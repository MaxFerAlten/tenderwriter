"""Project canonical operational events into the requirement graph.

This module is the bridge between TenderWriter's PostgreSQL canonical
state (tender_requirements, proposal_sections, contribution_units,
review_cycles, rework_actions, compliance_gates) and the Neo4j
``Requirement`` lifecycle projection.

Three responsibilities:

1. ``project_requirement_event`` — append a ``RequirementEvent`` node
   linked via ``HAS_LIFECYCLE_EVENT`` and update the snapshot fields on
   the parent ``Requirement`` according to a deterministic mapping from
   event type → snapshot delta.
2. ``refresh_requirement_snapshot`` — recompute the full snapshot for a
   requirement by reading the canonical state from PostgreSQL. Used as a
   fallback / reconciliation path so the projection cannot drift from
   the source of truth.
3. ``explain_requirement_path`` — read-only helper that returns the
   snapshot plus recent lifecycle events for a requirement, used by the
   intelligence agent / explain tool.

The projector is a *write* path on Neo4j only. It never mutates
PostgreSQL — that is the job of the workflow services that *call* it
after their own canonical write succeeded. This keeps the intelligence
layer's read-only contract intact for the operational tables.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceStatus,
    ContributionUnit,
    ContributionUnitStatus,
    ProposalSection,
    ReviewCycle,
    ReworkAction,
    ReworkStatus,
    SectionStatus,
    TenderRequirement,
)

logger = structlog.get_logger()


def requirement_node_id(tender_id: int | str, requirement_id: int | str) -> str:
    """Canonical Neo4j ``Requirement.id`` for a SQL tender_requirement row."""
    return f"tender-{tender_id}-requirement-{requirement_id}"


_active_rag_engine: Any | None = None


def set_active_rag_engine(engine: Any | None) -> None:
    """Register the application-wide RAG engine for opportunistic projection.

    Call from the FastAPI lifespan once the engine is initialised. The
    workflow services use this when no explicit ``rag_engine`` was passed
    to the projection helper.
    """
    global _active_rag_engine
    _active_rag_engine = engine


def get_active_rag_engine() -> Any | None:
    """Return the engine registered via :func:`set_active_rag_engine`."""
    return _active_rag_engine


_EVENT_SNAPSHOT_DELTAS: dict[str, dict[str, str]] = {
    # canonical operational events emitted by TenderWriter (see kpi_reason_engine)
    "requirements_extracted": {"current_status": "tracked", "coverage_status": "open"},
    "proposal_section_updated": {"current_status": "in_progress"},
    "contribution_request_created": {"coverage_status": "requested"},
    "contribution_received": {"coverage_status": "draft"},
    "contribution_review_started": {"current_status": "in_review"},
    "review_approved": {
        "current_status": "fully_addressed",
        "coverage_status": "covered",
        "risk_level": "green",
    },
    "review_changes_requested": {
        "current_status": "partially_addressed",
        "coverage_status": "rework",
        "risk_level": "amber",
    },
    "rework_requested": {"coverage_status": "rework", "risk_level": "amber"},
    "rework_resolved": {"risk_level": "green"},
    "compliance_gate_opened": {"gate_state": "open"},
    "compliance_gate_passed": {"gate_state": "passed"},
    "compliance_gate_failed": {"gate_state": "failed", "risk_level": "red"},
    "sla_breached": {"risk_level": "red"},
}


def _datetime_to_iso(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def derive_snapshot_delta(event_type: str) -> dict[str, str]:
    """Return the snapshot fields a given event type would set."""
    return dict(_EVENT_SNAPSHOT_DELTAS.get(event_type, {}))


def _graph_retriever(rag_engine: Any) -> Any | None:
    if rag_engine is None:
        return None
    return getattr(rag_engine, "graph_retriever", None)


@dataclass(slots=True)
class ProjectionResult:
    """Outcome of a single ``project_requirement_event`` call."""

    projected: bool
    snapshot_updated: bool
    requirement_node_id: str
    snapshot_delta: dict[str, str]
    error: str | None = None


async def project_requirement_event(
    *,
    rag_engine: Any,
    tender_id: int | str,
    requirement_id: int | str,
    event_type: str,
    occurred_at: datetime | str | None,
    external_event_id: str,
    actor_id: int | None = None,
    payload: Mapping[str, Any] | None = None,
) -> ProjectionResult:
    """Append a lifecycle event node and update the snapshot.

    Returns a :class:`ProjectionResult` describing the outcome. Failures
    are swallowed (logged + reported in ``error``) so the calling
    workflow path never aborts because the graph is unreachable.
    """
    node_id = requirement_node_id(tender_id, requirement_id)
    delta = derive_snapshot_delta(event_type)

    graph = _graph_retriever(rag_engine)
    if graph is None:
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=delta,
            error="graph retriever unavailable",
        )

    try:
        await rag_engine.ensure_initialized()
    except Exception as exc:
        logger.warning(
            "RAG engine unavailable during requirement event projection",
            tender_id=tender_id,
            requirement_id=requirement_id,
            event_type=event_type,
            error=str(exc),
        )
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=delta,
            error=str(exc),
        )

    occurred_iso = _datetime_to_iso(occurred_at) or _datetime_to_iso(datetime.now(timezone.utc))
    try:
        await graph.append_requirement_lifecycle_event(
            node_id,
            {
                "external_event_id": external_event_id,
                "event_type": event_type,
                "occurred_at": occurred_iso,
                "actor_id": actor_id,
                "tender_id": str(tender_id),
                "payload": dict(payload or {}),
            },
        )
    except Exception as exc:
        logger.warning(
            "Failed to project requirement lifecycle event",
            tender_id=tender_id,
            requirement_id=requirement_id,
            event_type=event_type,
            error=str(exc),
        )
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=delta,
            error=str(exc),
        )

    snapshot_payload: dict[str, Any] = dict(delta)
    snapshot_payload["last_event_type"] = event_type
    snapshot_payload["last_event_at"] = occurred_iso

    snapshot_updated = False
    try:
        await graph.update_requirement_snapshot(node_id, snapshot_payload)
        snapshot_updated = True
    except Exception as exc:
        logger.warning(
            "Failed to update requirement snapshot in graph",
            tender_id=tender_id,
            requirement_id=requirement_id,
            event_type=event_type,
            error=str(exc),
        )
        return ProjectionResult(
            projected=True,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=delta,
            error=str(exc),
        )

    return ProjectionResult(
        projected=True,
        snapshot_updated=snapshot_updated,
        requirement_node_id=node_id,
        snapshot_delta=delta,
    )


def _coverage_status_from_section(section: ProposalSection | None) -> str:
    if section is None:
        return "unmapped"
    status = section.status or SectionStatus.TODO
    if status == SectionStatus.APPROVED:
        return "covered"
    if status == SectionStatus.IN_REVIEW:
        return "in_review"
    if status == SectionStatus.IN_PROGRESS:
        return "draft"
    return "open"


def _current_status_from_compliance(
    compliance_status: ComplianceStatus | None,
    section: ProposalSection | None,
) -> str:
    if compliance_status == ComplianceStatus.FULLY_ADDRESSED:
        return "fully_addressed"
    if compliance_status == ComplianceStatus.PARTIALLY_ADDRESSED:
        return "partially_addressed"
    if section is not None and section.status == SectionStatus.IN_REVIEW:
        return "in_review"
    if section is not None and section.status == SectionStatus.IN_PROGRESS:
        return "in_progress"
    return "tracked"


def _risk_level_from_state(
    *,
    has_blocking_open_rework: bool,
    has_failed_gate: bool,
    has_open_rework: bool,
) -> str:
    if has_failed_gate or has_blocking_open_rework:
        return "red"
    if has_open_rework:
        return "amber"
    return "green"


def _gate_state_from_gates(gates: Sequence[ComplianceGate]) -> str:
    if not gates:
        return "none"
    statuses = {getattr(g.status, "value", g.status) for g in gates}
    if "failed" in statuses:
        return "failed"
    if "open" in statuses:
        return "open"
    if "passed" in statuses and len(statuses) == 1:
        return "passed"
    return "open"


async def _load_contributions_for_section(
    db: AsyncSession,
    *,
    section_id: int,
) -> list[ContributionUnit]:
    result = await db.execute(
        select(ContributionUnit)
        .where(ContributionUnit.proposal_section_id == section_id)
        .options(selectinload(ContributionUnit.tender))
    )
    return list(result.scalars().all())


async def _load_reviews_for_contribution(
    db: AsyncSession,
    *,
    contribution_id: int,
) -> list[ReviewCycle]:
    result = await db.execute(
        select(ReviewCycle).where(ReviewCycle.contribution_unit_id == contribution_id)
    )
    return list(result.scalars().all())


async def _load_reworks_for_contribution(
    db: AsyncSession,
    *,
    contribution_id: int,
) -> list[ReworkAction]:
    result = await db.execute(
        select(ReworkAction).where(ReworkAction.contribution_unit_id == contribution_id)
    )
    return list(result.scalars().all())


async def _load_gates_for_contribution(
    db: AsyncSession,
    *,
    contribution_id: int,
) -> list[ComplianceGate]:
    result = await db.execute(
        select(ComplianceGate).where(ComplianceGate.contribution_unit_id == contribution_id)
    )
    return list(result.scalars().all())


async def _load_requirement(
    db: AsyncSession,
    *,
    requirement_id: int,
) -> TenderRequirement | None:
    result = await db.execute(
        select(TenderRequirement)
        .where(TenderRequirement.id == requirement_id)
        .options(selectinload(TenderRequirement.proposal_section))
    )
    return result.scalar_one_or_none()


async def refresh_requirement_snapshot(
    *,
    rag_engine: Any,
    db: AsyncSession,
    requirement_id: int,
) -> ProjectionResult:
    """Recompute and write the full snapshot for ``requirement_id``.

    Reads the canonical state from PostgreSQL and projects the resulting
    snapshot into Neo4j. Does not append any event nodes — use this when
    you want to *reconcile* the projection with the source of truth.
    """
    requirement = await _load_requirement(db, requirement_id=requirement_id)
    if requirement is None:
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id="",
            snapshot_delta={},
            error="requirement not found",
        )

    node_id = requirement_node_id(requirement.tender_id, requirement.id)
    section = requirement.proposal_section
    coverage = _coverage_status_from_section(section)
    current = _current_status_from_compliance(requirement.compliance_status, section)

    has_open_rework = False
    has_blocking_open_rework = False
    gates: list[ComplianceGate] = []

    if section is not None:
        contributions = await _load_contributions_for_section(db, section_id=section.id)
        for contribution in contributions:
            if contribution.status == ContributionUnitStatus.REWORK:
                has_open_rework = True
            reworks = await _load_reworks_for_contribution(db, contribution_id=contribution.id)
            for rw in reworks:
                if rw.status == ReworkStatus.OPEN:
                    has_open_rework = True
                    if bool(getattr(rw, "is_blocking", False)):
                        has_blocking_open_rework = True
            gates.extend(await _load_gates_for_contribution(db, contribution_id=contribution.id))

    has_failed_gate = any(getattr(g.status, "value", g.status) == "failed" for g in gates)
    risk = _risk_level_from_state(
        has_blocking_open_rework=has_blocking_open_rework,
        has_failed_gate=has_failed_gate,
        has_open_rework=has_open_rework,
    )
    gate_state = _gate_state_from_gates(gates)

    snapshot = {
        "current_status": current,
        "coverage_status": coverage,
        "risk_level": risk,
        "gate_state": gate_state,
    }

    graph = _graph_retriever(rag_engine)
    if graph is None:
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=snapshot,
            error="graph retriever unavailable",
        )

    try:
        await rag_engine.ensure_initialized()
        await graph.update_requirement_snapshot(node_id, snapshot)
    except Exception as exc:
        logger.warning(
            "Failed to refresh requirement snapshot",
            requirement_id=requirement_id,
            error=str(exc),
        )
        return ProjectionResult(
            projected=False,
            snapshot_updated=False,
            requirement_node_id=node_id,
            snapshot_delta=snapshot,
            error=str(exc),
        )

    return ProjectionResult(
        projected=True,
        snapshot_updated=True,
        requirement_node_id=node_id,
        snapshot_delta=snapshot,
    )


async def _load_requirements_for_section(
    db: AsyncSession,
    *,
    section_id: int,
) -> list[TenderRequirement]:
    result = await db.execute(
        select(TenderRequirement).where(TenderRequirement.proposal_section_id == section_id)
    )
    return list(result.scalars().all())


async def project_workflow_events(
    *,
    db: AsyncSession,
    rag_engine: Any | None,
    tender_id: int,
    contribution: ContributionUnit,
    events: Sequence[tuple[str, Mapping[str, Any]]],
    actor_id: int | None = None,
) -> list[ProjectionResult]:
    """Project canonical workflow events onto every linked requirement.

    Resolves the contribution → proposal_section → tender_requirements
    chain once and then fans out each event to every requirement linked
    to the section. Events whose ``event_type`` has no snapshot delta
    are still appended to the lifecycle history (for audit) but do not
    change the snapshot.
    """
    engine = rag_engine if rag_engine is not None else get_active_rag_engine()
    if engine is None or not events:
        return []

    section_id = getattr(contribution, "proposal_section_id", None)
    if not section_id:
        return []

    requirements = await _load_requirements_for_section(db, section_id=section_id)
    if not requirements:
        return []

    results: list[ProjectionResult] = []
    for event_type, payload in events:
        external_event_id = (
            f"workflow-c{contribution.id}-{event_type}-"
            f"{payload.get('external_review_cycle_id') or payload.get('external_rework_id') or payload.get('external_request_id') or ''}"
            f"-{payload.get('completed_at') or payload.get('resolved_at') or payload.get('requested_at') or payload.get('started_at') or ''}"
        ).strip("-")
        for requirement in requirements:
            requirement_id = getattr(requirement, "id", None)
            if not requirement_id:
                continue
            scoped_event_id = f"{external_event_id}-r{requirement_id}"
            occurred_at = (
                payload.get("completed_at")
                or payload.get("resolved_at")
                or payload.get("requested_at")
                or payload.get("started_at")
                or payload.get("evaluated_at")
            )
            result = await project_requirement_event(
                rag_engine=engine,
                tender_id=tender_id,
                requirement_id=requirement_id,
                event_type=event_type,
                occurred_at=occurred_at,
                external_event_id=scoped_event_id,
                actor_id=actor_id,
                payload=dict(payload),
            )
            results.append(result)
    return results


async def project_gate_event(
    *,
    rag_engine: Any | None,
    db: AsyncSession,
    tender_id: int,
    gate: ComplianceGate,
    event_type: str,
    actor_id: int | None = None,
) -> list[ProjectionResult]:
    """Project a compliance gate transition onto every linked requirement.

    Walks gate → contribution_unit → proposal_section → requirements.
    """
    engine = rag_engine if rag_engine is not None else get_active_rag_engine()
    if engine is None:
        return []

    contribution_id = getattr(gate, "contribution_unit_id", None)
    if not contribution_id:
        return []

    contribution = await db.execute(
        select(ContributionUnit).where(ContributionUnit.id == contribution_id)
    )
    contribution_row = contribution.scalar_one_or_none()
    if contribution_row is None or not contribution_row.proposal_section_id:
        return []

    requirements = await _load_requirements_for_section(
        db, section_id=contribution_row.proposal_section_id
    )
    if not requirements:
        return []

    payload = {
        "external_gate_id": str(gate.id),
        "external_contribution_id": str(contribution_id),
        "gate_name": gate.gate_name,
        "status": getattr(gate.status, "value", gate.status),
    }
    occurred_at = getattr(gate, "evaluated_at", None) or getattr(gate, "due_at", None)

    results: list[ProjectionResult] = []
    for requirement in requirements:
        requirement_id = getattr(requirement, "id", None)
        if not requirement_id:
            continue
        external_event_id = f"gate-{gate.id}-{event_type}-r{requirement_id}"
        result = await project_requirement_event(
            rag_engine=engine,
            tender_id=tender_id,
            requirement_id=requirement_id,
            event_type=event_type,
            occurred_at=occurred_at,
            external_event_id=external_event_id,
            actor_id=actor_id,
            payload=payload,
        )
        results.append(result)
    return results


async def reconcile_tender_lifecycle_projection(
    *,
    rag_engine: Any,
    db: AsyncSession,
    tender_id: int,
) -> dict[str, Any]:
    """Rebuild every requirement projection for ``tender_id`` from PG truth.

    For each :class:`TenderRequirement` belonging to the tender, run
    :func:`refresh_requirement_snapshot` to re-derive coverage/risk/gate
    state from PostgreSQL and re-write it onto the Neo4j Requirement
    node. Lifecycle event nodes are not appended — graph idempotency for
    those is enforced by the ``RequirementEvent.external_event_id``
    UNIQUE constraint at projection time.

    Per-requirement failures are collected, not raised: a partial outage
    (e.g. one requirement whose section linkage is broken) must not
    block the rest of the tender from converging.
    """
    engine = rag_engine if rag_engine is not None else get_active_rag_engine()
    started_at = datetime.now(timezone.utc)

    if engine is None:
        return {
            "tender_id": tender_id,
            "requirements_seen": 0,
            "requirements_projected": 0,
            "requirements_failed": 0,
            "last_projected_at": _datetime_to_iso(started_at),
            "errors": ["graph retriever unavailable"],
        }

    requirements = (
        (
            await db.execute(
                select(TenderRequirement).where(TenderRequirement.tender_id == tender_id)
            )
        )
        .scalars()
        .all()
    )

    seen = len(requirements)
    projected = 0
    failed = 0
    errors: list[dict[str, Any]] = []

    for requirement in requirements:
        requirement_id = getattr(requirement, "id", None)
        if requirement_id is None:
            failed += 1
            errors.append({"requirement_id": None, "error": "missing requirement id"})
            continue
        try:
            result = await refresh_requirement_snapshot(
                rag_engine=engine, db=db, requirement_id=int(requirement_id)
            )
        except Exception as exc:  # pragma: no cover - defensive
            failed += 1
            errors.append({"requirement_id": int(requirement_id), "error": str(exc)})
            logger.warning(
                "lifecycle_reconcile.requirement_crashed",
                tender_id=tender_id,
                requirement_id=requirement_id,
                error=str(exc),
            )
            continue

        if result.snapshot_updated:
            projected += 1
        else:
            failed += 1
            errors.append(
                {
                    "requirement_id": int(requirement_id),
                    "error": result.error or "snapshot not updated",
                }
            )

    finished_at = datetime.now(timezone.utc)
    summary = {
        "tender_id": tender_id,
        "requirements_seen": seen,
        "requirements_projected": projected,
        "requirements_failed": failed,
        "last_projected_at": _datetime_to_iso(finished_at),
        "errors": errors,
    }
    logger.info(
        "lifecycle_reconcile.completed",
        tender_id=tender_id,
        requirements_seen=seen,
        requirements_projected=projected,
        requirements_failed=failed,
    )
    return summary


async def explain_requirement_path(
    *,
    rag_engine: Any,
    tender_id: int | str,
    requirement_id: int | str,
    limit: int = 25,
) -> dict[str, Any]:
    """Return ``{"snapshot": {...}, "events": [...], "node_id": ...}``.

    Read-only convenience wrapper used by the intelligence agent. When the
    graph is unreachable, returns empty containers without raising.
    """
    node_id = requirement_node_id(tender_id, requirement_id)
    graph = _graph_retriever(rag_engine)
    empty = {"node_id": node_id, "snapshot": {}, "events": []}
    if graph is None:
        return empty

    try:
        await rag_engine.ensure_initialized()
        data = await graph.fetch_requirement_lifecycle(node_id, limit=limit)
    except Exception as exc:
        logger.warning(
            "Failed to fetch requirement lifecycle from graph",
            requirement_id=requirement_id,
            error=str(exc),
        )
        return empty

    return {"node_id": node_id, **data}
