"""TenderRehearsalService — Wave-3 orchestrator.

The service is a *persistent* orchestration layer over the existing
Wave-1 / Wave-2 tools.  It never writes back to canonical workflow
tables (``review_cycles`` / ``rework_actions`` / ``compliance_gates``):
it only writes to ``rehearsal_runs`` / ``rehearsal_persona_results`` /
``rehearsal_recommendations``.  Conversion of a recommendation into a
real ``ReworkAction`` happens in PR-09, behind an explicit accept
action.

Call flow:

    create_rehearsal_run()   ← synchronous, returns row in status=PENDING
           │
           ▼
    Celery task (run_rehearsal_task)
           │
           ▼
    TenderRehearsalService.execute_run(run_id)
           │
           ├─ load run + resolve personas from snapshot
           ├─ run the 4 Wave-1/2 tools once per run (shared across personas)
           ├─ evaluate_persona() for each persona
           ├─ derive recommendations from high-severity findings
           └─ persist persona_results + recommendations + report_json

All heavy lifting (coverage analysis, evidence audit, compliance
panorama, contradiction detection) happens inside the already-tested
tools; this module only orchestrates and persists.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.intelligence.persona_catalog import PERSONA_CATALOG, resolve_personas
from app.intelligence.personas import (
    PERSONA_CATALOG_VERSION,
    ReviewerPersona,
    persona_as_dict,
)
from app.intelligence.rehearsal_runner import (
    PersonaEvaluation,
    counts_by_severity,
    evaluate_persona,
)
from app.intelligence.rehearsal_summary import build_rehearsal_summary
from app.intelligence.tool_registry import TenderToolRegistry
from app.models import (
    RehearsalPersonaResult,
    RehearsalRecommendation,
    RehearsalRecommendationStatus,
    RehearsalRun,
    RehearsalRunStatus,
)

logger = logging.getLogger(__name__)


REHEARSAL_REPORT_VERSION = "tw-rehearsal-v1"
_RECOMMENDATION_SEVERITY_MIN = {"high"}


_HEALTH_THRESHOLDS = (
    (80.0, "green"),
    (60.0, "amber"),
    (0.0, "red"),
)


def _map_score_to_health(score: float | None) -> str | None:
    if score is None:
        return None
    for threshold, label in _HEALTH_THRESHOLDS:
        if score >= threshold:
            return label
    return "red"


def _snapshot_personas(personas: Iterable[ReviewerPersona]) -> list[dict[str, Any]]:
    return [persona_as_dict(p) for p in personas]


def _derive_recommendations(
    persona_evaluations: list[PersonaEvaluation],
) -> list[dict[str, Any]]:
    """Collapse high-severity persona findings into rework suggestions.

    Findings that carry the same ``scope_type:scope_id`` are merged:
    the first persona to surface the issue keeps authorship, but the
    rationale enumerates every persona that agreed.  ``is_blocking``
    fires when at least two personas flag the scope at ``high`` severity.
    """

    by_scope: dict[tuple[str, str], dict[str, Any]] = {}
    for evaluation in persona_evaluations:
        for finding in evaluation.findings:
            severity = str(finding.get("severity") or "medium").casefold()
            if severity not in _RECOMMENDATION_SEVERITY_MIN:
                continue
            scope_type = str(finding.get("scope_type") or "requirement")
            scope_id = str(finding.get("scope_id") or "")
            if not scope_id:
                continue
            key = (scope_type, scope_id)
            bucket = by_scope.get(key)
            if bucket is None:
                bucket = {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "severity": severity,
                    "is_blocking": False,
                    "rationale": str(finding.get("summary") or "")[:2000],
                    "suggested_owner_role": _infer_owner(scope_type, finding),
                    "source_persona_id": evaluation.persona_id,
                    "concurring_personas": [evaluation.persona_id],
                }
                by_scope[key] = bucket
            else:
                if evaluation.persona_id not in bucket["concurring_personas"]:
                    bucket["concurring_personas"].append(evaluation.persona_id)
                bucket["is_blocking"] = len(bucket["concurring_personas"]) >= 2

    return sorted(
        by_scope.values(),
        key=lambda item: (
            0 if item["is_blocking"] else 1,
            item["scope_type"],
            item["scope_id"],
        ),
    )


def _infer_owner(scope_type: str, finding: dict[str, Any]) -> str | None:
    category = str(finding.get("category") or "").casefold()
    if scope_type == "gate":
        return "compliance"
    if category == "weak_evidence":
        return "bid_manager"
    if category == "contradiction":
        return "technical"
    if category == "coverage_gap":
        return "bid_manager"
    if category in {"compliance_risk"}:
        return "compliance"
    return None


class TenderRehearsalService:
    """Loads rehearsal runs and orchestrates persona evaluations."""

    def __init__(self, registry: TenderToolRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> TenderToolRegistry:
        return self._registry

    async def create_rehearsal_run(
        self,
        db: AsyncSession,
        *,
        tender_id: int,
        proposal_id: int,
        mode: str,
        persona_ids: list[str],
        proposal_section_ids: list[int],
        include_forecast_context: bool,
        requested_by: int | None,
    ) -> RehearsalRun:
        """Insert a PENDING run row and return it.

        The persona list is validated and snapshotted into
        ``context_snapshot_json`` so later catalog bumps cannot
        retroactively alter a past run's inputs.
        """

        personas = resolve_personas(persona_ids)
        snapshot = {
            "persona_catalog_version": PERSONA_CATALOG_VERSION,
            "personas": _snapshot_personas(personas),
            "persona_ids": [p.persona_id for p in personas],
            "proposal_section_ids": list(proposal_section_ids),
            "mode": mode,
            "include_forecast_context": bool(include_forecast_context),
        }
        run = RehearsalRun(
            tender_id=tender_id,
            proposal_id=proposal_id,
            mode=mode,
            status=RehearsalRunStatus.PENDING,
            requested_by=requested_by,
            context_snapshot_json=snapshot,
            version=REHEARSAL_REPORT_VERSION,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    async def execute_run(self, db: AsyncSession, *, run_id: int) -> RehearsalRun:
        """Execute a PENDING/FAILED rehearsal run to completion.

        The caller is responsible for transactionality: ``execute_run``
        commits its own progress markers (RUNNING, COMPLETED, FAILED)
        and the persona_results / recommendations rows.

        Idempotency: if the run is already in terminal state
        (``COMPLETED`` / ``CANCELLED``) this returns it unchanged.
        If it is already ``RUNNING`` the call re-runs — re-running an
        orphaned task is cheap and deterministic because the tool
        outputs are reproducible and the persona_results are cleared
        before re-insertion.
        """

        run = await self._load_run(db, run_id=run_id)
        if run is None:
            raise ValueError(f"rehearsal_run id={run_id} not found")

        if run.status in {RehearsalRunStatus.COMPLETED, RehearsalRunStatus.CANCELLED}:
            return run

        run.status = RehearsalRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        run.error_message = None
        await db.commit()

        try:
            personas = self._personas_from_snapshot(run)
            tool_outputs = await self._run_intelligence_tools(db, tender_id=run.tender_id)

            persona_evaluations: list[PersonaEvaluation] = []
            for persona in personas:
                evaluation = evaluate_persona(
                    persona=persona,
                    tool_outputs=tool_outputs,
                )
                persona_evaluations.append(evaluation)

            recommendations = _derive_recommendations(persona_evaluations)

            overall_score = (
                round(mean([e.score for e in persona_evaluations]), 2)
                if persona_evaluations
                else None
            )
            persona_divergence = (
                round(pstdev([e.score for e in persona_evaluations]), 2)
                if len(persona_evaluations) > 1
                else 0.0
            )

            await self._replace_persona_results(
                db,
                run_id=run.id,
                evaluations=persona_evaluations,
            )
            await self._replace_recommendations(
                db,
                run_id=run.id,
                recommendations=recommendations,
            )

            run.overall_score = overall_score
            run.persona_divergence = persona_divergence
            run.health_projection = _map_score_to_health(overall_score)
            run.status = RehearsalRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            run.report_json = {
                "overall_score": overall_score,
                "health_projection": run.health_projection,
                "persona_divergence": persona_divergence,
                "persona_scores": [
                    {
                        "persona_id": e.persona_id,
                        "display_name": e.display_name,
                        "reviewer_type": e.reviewer_type,
                        "score": e.score,
                        "severity_counts": counts_by_severity(e.findings),
                    }
                    for e in persona_evaluations
                ],
                "recommended_reworks_count": len(recommendations),
                "version": REHEARSAL_REPORT_VERSION,
            }
            await db.commit()
            sync_status = await self._publish_rehearsal_summary(
                db, tender_id=run.tender_id, proposal_id=run.proposal_id
            )
            run.kpi_summary_sync_status = sync_status  # transient, not persisted
            return run
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "rehearsal.execute_run.failed",
                extra={"run_id": run_id, "tender_id": run.tender_id},
            )
            run.status = RehearsalRunStatus.FAILED
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(UTC)
            await db.commit()
            raise

    async def _load_run(self, db: AsyncSession, *, run_id: int) -> RehearsalRun | None:
        result = await db.execute(
            select(RehearsalRun)
            .where(RehearsalRun.id == run_id)
            .options(
                selectinload(RehearsalRun.persona_results),
                selectinload(RehearsalRun.recommendations),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _personas_from_snapshot(run: RehearsalRun) -> list[ReviewerPersona]:
        snapshot = run.context_snapshot_json or {}
        persona_ids = snapshot.get("persona_ids") or list(PERSONA_CATALOG)
        personas: list[ReviewerPersona] = []
        for persona_id in persona_ids:
            candidate = PERSONA_CATALOG.get(persona_id)
            if candidate is not None:
                personas.append(candidate)
        if not personas:
            personas = list(PERSONA_CATALOG.values())
        return personas

    async def _run_intelligence_tools(
        self,
        db: AsyncSession,
        *,
        tender_id: int,
    ) -> dict[str, Any]:
        """Run the four tools once; reuse the outputs across personas."""

        outputs: dict[str, Any] = {}
        for tool_name, inputs in (
            ("coverage_analyzer", {"tender_id": tender_id}),
            ("evidence_auditor", {"tender_id": tender_id}),
            ("compliance_panorama", {"tender_id": tender_id}),
            ("contradiction_finder", {"tender_id": tender_id}),
        ):
            if not self._registry.contains(tool_name):
                outputs[tool_name] = {}
                continue
            try:
                outputs[tool_name] = await self._registry.run(tool_name, db, inputs)
            except Exception:
                logger.exception(
                    "rehearsal.tool_failed",
                    extra={"tool": tool_name, "tender_id": tender_id},
                )
                outputs[tool_name] = {}
        return outputs

    async def _replace_persona_results(
        self,
        db: AsyncSession,
        *,
        run_id: int,
        evaluations: list[PersonaEvaluation],
    ) -> None:
        existing = await db.execute(
            select(RehearsalPersonaResult).where(
                RehearsalPersonaResult.rehearsal_run_id == run_id,
            )
        )
        for row in existing.scalars().all():
            await db.delete(row)

        for evaluation in evaluations:
            counts = counts_by_severity(evaluation.findings)
            blocking_count = sum(
                1
                for finding in evaluation.findings
                if finding.get("severity") == "high" and finding.get("scope_type") == "gate"
            )
            db.add(
                RehearsalPersonaResult(
                    rehearsal_run_id=run_id,
                    persona_id=evaluation.persona_id,
                    display_name=evaluation.display_name,
                    reviewer_type=evaluation.reviewer_type,
                    score=evaluation.score,
                    blocking_findings_count=blocking_count,
                    high_severity_findings_count=counts.get("high", 0),
                    findings_json=evaluation.findings,
                    questions_json=evaluation.questions,
                    metrics_json=evaluation.metrics,
                )
            )

    async def _replace_recommendations(
        self,
        db: AsyncSession,
        *,
        run_id: int,
        recommendations: list[dict[str, Any]],
    ) -> None:
        existing = await db.execute(
            select(RehearsalRecommendation).where(
                RehearsalRecommendation.rehearsal_run_id == run_id,
            )
        )
        for row in existing.scalars().all():
            # Preserve recommendations that have already been accepted
            # or dismissed — overwriting them would silently discard
            # operator decisions.
            if row.status != RehearsalRecommendationStatus.PROPOSED:
                continue
            await db.delete(row)

        for recommendation in recommendations:
            db.add(
                RehearsalRecommendation(
                    rehearsal_run_id=run_id,
                    scope_type=recommendation["scope_type"],
                    scope_id=recommendation["scope_id"],
                    severity=recommendation["severity"],
                    is_blocking=recommendation["is_blocking"],
                    rationale=recommendation["rationale"],
                    suggested_owner_role=recommendation.get("suggested_owner_role"),
                    source_persona_id=recommendation["source_persona_id"],
                    status=RehearsalRecommendationStatus.PROPOSED,
                )
            )

    async def _publish_rehearsal_summary(
        self,
        db: AsyncSession,
        *,
        tender_id: int,
        proposal_id: int | None,
    ) -> str:
        """Push rehearsal summary to kpi-reason-engine. Best-effort, flag-gated.

        Returns one of: ``disabled``, ``no_summary``, ``delivered``,
        ``undelivered``, ``failed``. Never raises — KPI sync issues must
        never fail a completed rehearsal run.
        """
        if not getattr(settings, "rehearsal_summary_publish_enabled", False):
            return "disabled"
        try:
            summary = await build_rehearsal_summary(
                db, tender_id=tender_id, proposal_id=proposal_id
            )
            if summary is None:
                return "no_summary"
            from app.services.kpi_reason_engine import KpiReasonEngineClient

            client = KpiReasonEngineClient()
            result = await client.put_rehearsal_summary(str(tender_id), summary)
            if not result.delivered:
                logger.warning(
                    "rehearsal.publish_summary.undelivered",
                    extra={
                        "tender_id": tender_id,
                        "status_code": result.status_code,
                        "error": result.error_message,
                    },
                )
                return "undelivered"
            return "delivered"
        except Exception:
            logger.exception(
                "rehearsal.publish_summary.failed",
                extra={"tender_id": tender_id},
            )
            return "failed"


__all__ = [
    "REHEARSAL_REPORT_VERSION",
    "TenderRehearsalService",
]
