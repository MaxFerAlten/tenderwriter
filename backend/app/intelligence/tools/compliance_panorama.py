"""CompliancePanorama — adapter tool over the KPI reason engine.

The MiroFish ``PanoramaSearch`` primitive answered "what is the state of
the world?" in a single compact document. TenderWriter already has that
answer: the KPI reason engine publishes a tender snapshot with health
classes (green/amber/red), analytical phase (S0..S13) and forecast
signals. This tool is the server-side adapter that surfaces those
signals to the intelligence layer without recomputing them.

It is intentionally thin:

* read health/analytical phase from the KPI snapshot;
* count compliance gates and blocking reworks from the local DB (cheap,
  already in the session);
* summarise unresolved requirements via the same coverage source used by
  :class:`CoverageAnalyzer`.

All writes go through the KPI engine via existing paths — this tool only
*reads*.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceGateStatus,
    ComplianceStatus,
    ContributionUnit,
    Proposal,
    ReworkAction,
    ReworkStatus,
    Tender,
    TenderRequirement,
)
from app.services.compliance_observability import (
    AUTO_COMPLIANCE_GATE_NAME,
    build_compliance_requirement_coverage,
)
from app.services.kpi_reason_engine import KpiReasonEngineClient

_HEALTH_ORDER = ("green", "amber", "red")


def _pick_worst_health(*values: str | None) -> str:
    worst_index = 0
    for value in values:
        if value is None:
            continue
        casefolded = value.casefold()
        if casefolded in _HEALTH_ORDER:
            worst_index = max(worst_index, _HEALTH_ORDER.index(casefolded))
    return _HEALTH_ORDER[worst_index]


class CompliancePanorama:
    """Wave-1 adapter that unifies KPI snapshot and local gate signals."""

    name = "compliance_panorama"
    description = (
        "Returns the consolidated tender health panorama (green/amber/red), "
        "analytical phase, auto-gate status and blocking bottlenecks. Thin "
        "adapter over the KPI reason engine — read-only."
    )
    input_keys = ("tender_id",)

    def __init__(self, kpi_client: KpiReasonEngineClient | None = None) -> None:
        self._kpi_client = kpi_client or KpiReasonEngineClient()

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        tender_id = inputs.get("tender_id")
        if tender_id is None:
            raise ValueError("compliance_panorama requires 'tender_id'")
        tender = await self._load_tender(db, int(tender_id))
        if tender is None:
            return self._empty_result(int(tender_id))

        gate_counts, auto_gate_status = await self._count_gates(db, int(tender_id))
        blocking_reworks = await self._count_blocking_reworks(db, int(tender_id))
        coverage_items = build_compliance_requirement_coverage(tender)
        unresolved = [
            item
            for item in coverage_items
            if item.compliance_status != ComplianceStatus.FULLY_ADDRESSED
        ]
        high_priority_unresolved = sum(
            1 for item in unresolved if (item.priority or "medium").casefold() == "high"
        )

        snapshot_payload = await self._fetch_snapshot(str(tender.id))
        analytical_phase = snapshot_payload.get("analytical_phase") if snapshot_payload else None
        snapshot_health = snapshot_payload.get("health") if snapshot_payload else None

        local_health = self._local_health(
            failed_gates=gate_counts["failed"],
            open_gates=gate_counts["open"],
            blocking_reworks=blocking_reworks,
            high_priority_unresolved=high_priority_unresolved,
        )
        health = _pick_worst_health(local_health, snapshot_health)

        summary = {
            "failed_gates": gate_counts["failed"],
            "open_gates": gate_counts["open"],
            "blocking_reworks": blocking_reworks,
            "unresolved_requirements": len(unresolved),
            "high_priority_unresolved": high_priority_unresolved,
        }
        top_risks = self._top_risks(
            gate_counts=gate_counts,
            blocking_reworks=blocking_reworks,
            high_priority_unresolved=high_priority_unresolved,
        )
        return {
            "tender_id": int(tender.id),
            "health": health,
            "analytical_phase": analytical_phase,
            "auto_gate_status": auto_gate_status,
            "summary": summary,
            "top_risks": top_risks,
            "kpi_snapshot_delivered": snapshot_payload is not None,
        }

    async def _load_tender(self, db: AsyncSession, tender_id: int) -> Tender | None:
        result = await db.execute(
            select(Tender)
            .where(Tender.id == tender_id)
            .options(
                selectinload(Tender.requirements).selectinload(TenderRequirement.proposal_section),
                selectinload(Tender.consolidated_requirements),
                selectinload(Tender.proposals).selectinload(Proposal.sections),
            )
        )
        return result.scalar_one_or_none()

    async def _count_gates(
        self,
        db: AsyncSession,
        tender_id: int,
    ) -> tuple[dict[str, int], str | None]:
        result = await db.execute(
            select(ComplianceGate).where(ComplianceGate.tender_id == tender_id)
        )
        gates = list(result.scalars())
        counts = {"open": 0, "passed": 0, "failed": 0}
        auto_gate_status: str | None = None
        for gate in gates:
            status = gate.status or ComplianceGateStatus.OPEN
            counts[status.value] = counts.get(status.value, 0) + 1
            if gate.gate_name == AUTO_COMPLIANCE_GATE_NAME:
                auto_gate_status = status.value
        return counts, auto_gate_status

    async def _count_blocking_reworks(self, db: AsyncSession, tender_id: int) -> int:
        result = await db.execute(
            select(ReworkAction)
            .join(ContributionUnit, ContributionUnit.id == ReworkAction.contribution_unit_id)
            .where(
                ContributionUnit.tender_id == tender_id,
                ReworkAction.status == ReworkStatus.OPEN,
                ReworkAction.is_blocking.is_(True),
            )
        )
        return len(list(result.scalars()))

    async def _fetch_snapshot(self, external_tender_id: str) -> dict[str, Any] | None:
        try:
            result = await self._kpi_client.get_tender_snapshot(external_tender_id)
        except Exception:
            return None
        if not result.delivered:
            return None
        return dict(result.response_json or {})

    @staticmethod
    def _local_health(
        *,
        failed_gates: int,
        open_gates: int,
        blocking_reworks: int,
        high_priority_unresolved: int,
    ) -> str:
        if failed_gates > 0 or blocking_reworks > 0 or high_priority_unresolved >= 3:
            return "red"
        if open_gates > 0 or high_priority_unresolved > 0:
            return "amber"
        return "green"

    @staticmethod
    def _top_risks(
        *,
        gate_counts: Mapping[str, int],
        blocking_reworks: int,
        high_priority_unresolved: int,
    ) -> list[dict[str, str]]:
        risks: list[dict[str, str]] = []
        if gate_counts.get("failed", 0):
            risks.append(
                {
                    "code": "failed_gate",
                    "severity": "critical",
                    "summary": f"{gate_counts['failed']} failed compliance gate(s) still reflected in telemetry.",
                }
            )
        if blocking_reworks:
            risks.append(
                {
                    "code": "blocking_rework",
                    "severity": "high",
                    "summary": f"{blocking_reworks} blocking rework action(s) still open.",
                }
            )
        if high_priority_unresolved:
            risks.append(
                {
                    "code": "unresolved_high_priority_requirements",
                    "severity": "high" if high_priority_unresolved >= 3 else "medium",
                    "summary": f"{high_priority_unresolved} high-priority requirement(s) without full coverage.",
                }
            )
        if gate_counts.get("open", 0) and not risks:
            risks.append(
                {
                    "code": "open_gate",
                    "severity": "medium",
                    "summary": f"{gate_counts['open']} compliance gate(s) still open.",
                }
            )
        return risks

    def _empty_result(self, tender_id: int) -> dict[str, Any]:
        return {
            "tender_id": tender_id,
            "health": "green",
            "analytical_phase": None,
            "auto_gate_status": None,
            "summary": {
                "failed_gates": 0,
                "open_gates": 0,
                "blocking_reworks": 0,
                "unresolved_requirements": 0,
                "high_priority_unresolved": 0,
            },
            "top_risks": [],
            "kpi_snapshot_delivered": False,
        }


__all__ = ["CompliancePanorama"]
