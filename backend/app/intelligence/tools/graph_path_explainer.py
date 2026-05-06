"""GraphPathExplainer — deterministic walk over the requirement → section
→ contribution → review/rework/gate chain.

The MiroFish ``PanoramaSearch`` traversed an Episode-rich Zep graph; we
don't need that here because TenderWriter already stores the canonical
state in PostgreSQL. The explainer is a *thin* SQL walker that surfaces
the chain a human can follow when triaging "why is this requirement
stuck?".

The tool is read-only. It never mutates the database. It also avoids any
LLM call: the path is assembled from joins and rendered with stable
templates so the answer is reproducible and auditable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceStatus,
    ConsolidatedRequirement,
    ContributionUnit,
    ProposalSection,
    ReviewCycle,
    ReworkAction,
    TenderRequirement,
)


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", str(value))


class GraphPathExplainer:
    """Wave-2 explainability tool — deterministic, LLM-free."""

    name = "graph_path_explainer"
    description = (
        "Explains the chain requirement → proposal section → contribution unit "
        "→ review/rework/compliance gate so a triager can see why a requirement "
        "is in its current state. Read-only, deterministic."
    )
    input_keys = ("tender_id", "requirement_id")

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        tender_id = inputs.get("tender_id")
        requirement_id = inputs.get("requirement_id")
        if tender_id is None:
            raise ValueError("graph_path_explainer requires 'tender_id'")
        if requirement_id is None:
            raise ValueError("graph_path_explainer requires 'requirement_id'")

        tender_id_int = int(tender_id)
        requirement_id_int = int(requirement_id)

        requirement = await self._load_requirement(db, tender_id_int, requirement_id_int)
        if requirement is None:
            return {
                "tender_id": tender_id_int,
                "requirement_id": requirement_id_int,
                "found": False,
                "narrative": (
                    f"Nessun requisito #{requirement_id_int} trovato per la gara #{tender_id_int}."
                ),
                "path": [],
            }

        section_id = self._section_id(requirement)
        section = await self._load_section(db, section_id) if section_id else None
        contributions = await self._load_contributions(db, tender_id_int, section_id)
        reviews = await self._load_reviews(db, [c.id for c in contributions])
        reworks = await self._load_reworks(db, [c.id for c in contributions])
        gates = await self._load_gates(db, tender_id_int, [c.id for c in contributions])

        path = self._assemble_path(
            requirement=requirement,
            section=section,
            contributions=contributions,
            reviews=reviews,
            reworks=reworks,
            gates=gates,
        )
        return {
            "tender_id": tender_id_int,
            "requirement_id": requirement_id_int,
            "found": True,
            "narrative": self._narrative(path),
            "path": [step for step in path],
        }

    async def _load_requirement(
        self,
        db: AsyncSession,
        tender_id: int,
        requirement_id: int,
    ) -> TenderRequirement | ConsolidatedRequirement | None:
        result = await db.execute(
            select(TenderRequirement)
            .where(
                TenderRequirement.tender_id == tender_id,
                TenderRequirement.id == requirement_id,
            )
            .options(selectinload(TenderRequirement.proposal_section))
        )
        requirement = result.scalar_one_or_none()
        if requirement is not None:
            return requirement

        result = await db.execute(
            select(ConsolidatedRequirement).where(
                ConsolidatedRequirement.tender_id == tender_id,
                ConsolidatedRequirement.id == requirement_id,
            )
        )
        return result.scalar_one_or_none()

    async def _load_section(self, db: AsyncSession, section_id: int) -> ProposalSection | None:
        result = await db.execute(
            select(ProposalSection)
            .where(ProposalSection.id == section_id)
            .options(selectinload(ProposalSection.proposal))
        )
        return result.scalar_one_or_none()

    async def _load_contributions(
        self,
        db: AsyncSession,
        tender_id: int,
        section_id: int | None,
    ) -> list[ContributionUnit]:
        if section_id is None:
            return []
        result = await db.execute(
            select(ContributionUnit).where(
                ContributionUnit.tender_id == tender_id,
                ContributionUnit.proposal_section_id == section_id,
            )
        )
        return list(result.scalars())

    async def _load_reviews(
        self,
        db: AsyncSession,
        contribution_ids: list[int],
    ) -> list[ReviewCycle]:
        if not contribution_ids:
            return []
        result = await db.execute(
            select(ReviewCycle).where(ReviewCycle.contribution_unit_id.in_(contribution_ids))
        )
        return list(result.scalars())

    async def _load_reworks(
        self,
        db: AsyncSession,
        contribution_ids: list[int],
    ) -> list[ReworkAction]:
        if not contribution_ids:
            return []
        result = await db.execute(
            select(ReworkAction).where(ReworkAction.contribution_unit_id.in_(contribution_ids))
        )
        return list(result.scalars())

    async def _load_gates(
        self,
        db: AsyncSession,
        tender_id: int,
        contribution_ids: list[int],
    ) -> list[ComplianceGate]:
        if not contribution_ids:
            result = await db.execute(
                select(ComplianceGate).where(ComplianceGate.tender_id == tender_id)
            )
            return list(result.scalars())
        result = await db.execute(
            select(ComplianceGate).where(
                ComplianceGate.tender_id == tender_id,
                ComplianceGate.contribution_unit_id.in_(contribution_ids),
            )
        )
        return list(result.scalars())

    @staticmethod
    def _section_id(
        requirement: TenderRequirement | ConsolidatedRequirement,
    ) -> int | None:
        section_id = getattr(requirement, "proposal_section_id", None)
        if section_id is None:
            metadata = getattr(requirement, "metadata_json", None) or {}
            if isinstance(metadata, Mapping):
                mapping = metadata.get("proposal_section_id")
                try:
                    section_id = int(mapping) if mapping is not None else None
                except (TypeError, ValueError):
                    section_id = None
        return int(section_id) if section_id is not None else None

    @staticmethod
    def _assemble_path(
        *,
        requirement: TenderRequirement | ConsolidatedRequirement,
        section: ProposalSection | None,
        contributions: list[ContributionUnit],
        reviews: list[ReviewCycle],
        reworks: list[ReworkAction],
        gates: list[ComplianceGate],
    ) -> list[dict[str, Any]]:
        path: list[dict[str, Any]] = []

        compliance_status = getattr(requirement, "compliance_status", None)
        path.append(
            {
                "kind": "requirement",
                "id": int(requirement.id),
                "label": (
                    getattr(requirement, "requirement_text", None)
                    or getattr(requirement, "canonical_text", None)
                    or ""
                )[:280],
                "priority": getattr(requirement, "priority", None) or "medium",
                "compliance_status": _enum_value(compliance_status)
                if isinstance(compliance_status, ComplianceStatus)
                else compliance_status,
            }
        )
        if section is not None:
            path.append(
                {
                    "kind": "section",
                    "id": int(section.id),
                    "label": section.title or f"Section #{section.id}",
                    "status": _enum_value(getattr(section, "status", None)),
                }
            )
        for contribution in contributions:
            path.append(
                {
                    "kind": "contribution",
                    "id": int(contribution.id),
                    "label": contribution.title,
                    "status": _enum_value(contribution.status),
                    "department": contribution.department_name,
                }
            )
        for review in reviews:
            path.append(
                {
                    "kind": "review",
                    "id": int(review.id),
                    "label": review.stage_name or "review",
                    "status": _enum_value(review.status),
                    "outcome": review.outcome,
                }
            )
        for rework in reworks:
            path.append(
                {
                    "kind": "rework",
                    "id": int(rework.id),
                    "label": (rework.reason or "rework")[:280],
                    "status": _enum_value(rework.status),
                    "is_blocking": bool(rework.is_blocking),
                    "severity": rework.severity,
                }
            )
        for gate in gates:
            path.append(
                {
                    "kind": "gate",
                    "id": int(gate.id),
                    "label": gate.gate_name,
                    "status": _enum_value(gate.status),
                }
            )
        return path

    @staticmethod
    def _narrative(path: list[dict[str, Any]]) -> str:
        if not path:
            return "Nessun nodo nel grafo."
        parts: list[str] = []
        for step in path:
            kind = step.get("kind")
            label = (step.get("label") or "").strip()
            label_short = label[:80] + "…" if len(label) > 80 else label
            if kind == "requirement":
                parts.append(
                    f"Requirement #{step['id']} ({step.get('priority', 'medium')}): {label_short}"
                )
            elif kind == "section":
                parts.append(f'Section #{step["id"]} "{label_short}" [{step.get("status", "?")}]')
            elif kind == "contribution":
                parts.append(
                    f'Contribution #{step["id"]} "{label_short}" [{step.get("status", "?")}]'
                )
            elif kind == "review":
                parts.append(f"Review #{step['id']} {label_short} [{step.get('status', '?')}]")
            elif kind == "rework":
                blocking = " (blocking)" if step.get("is_blocking") else ""
                parts.append(
                    f"Rework #{step['id']}{blocking} [{step.get('status', '?')}]: {label_short}"
                )
            elif kind == "gate":
                parts.append(f'Gate #{step["id"]} "{label_short}" [{step.get("status", "?")}]')
        return " → ".join(parts)


__all__ = ["GraphPathExplainer"]
