"""CoverageAnalyzer — requirement-to-section coverage audit.

Answers:

- quali requirement non sono coperti (``uncovered``)?
- quali sono solo parzialmente coperti (``partially_covered``)?
- quale dominio ontologico è scoperto?

The tool is read-only: it re-uses
``build_compliance_requirement_coverage`` so the answers always match the
compliance observability view that the UI already shows. It does not
invent a second semantics — it merely groups and tags the same data.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.intelligence.ontology import TenderOntologyService, default_ontology_service
from app.models import (
    ComplianceStatus,
    Proposal,
    Tender,
    TenderRequirement,
)
from app.services.compliance_observability import (
    ComplianceRequirementCoverage,
    build_compliance_requirement_coverage,
)

_COVERAGE_STATUS_BY_COMPLIANCE = {
    ComplianceStatus.FULLY_ADDRESSED: "fully_covered",
    ComplianceStatus.PARTIALLY_ADDRESSED: "partially_covered",
    ComplianceStatus.NOT_ADDRESSED: "uncovered",
}


def _coverage_status(coverage: ComplianceRequirementCoverage) -> str:
    return _COVERAGE_STATUS_BY_COMPLIANCE.get(coverage.compliance_status, "uncovered")


class CoverageAnalyzer:
    """Wave-1 coverage tool. Deterministic, LLM-free."""

    name = "coverage_analyzer"
    description = (
        "Audits how well proposal sections cover the tender requirements and "
        "groups gaps by ontology domain. Read-only."
    )
    input_keys = ("tender_id",)

    def __init__(self, ontology_service: TenderOntologyService | None = None) -> None:
        self._ontology = ontology_service or default_ontology_service()

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        tender_id = inputs.get("tender_id")
        if tender_id is None:
            raise ValueError("coverage_analyzer requires 'tender_id'")
        tender = await self._load_tender(db, int(tender_id))
        if tender is None:
            return {
                "tender_id": int(tender_id),
                "summary": {
                    "total_requirements": 0,
                    "fully_covered": 0,
                    "partially_covered": 0,
                    "uncovered": 0,
                    "high_priority_uncovered": 0,
                },
                "by_domain": [],
                "gaps": [],
            }

        coverage_items = build_compliance_requirement_coverage(tender)
        return self._summarise(tender_id=int(tender_id), coverage_items=coverage_items)

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

    def _summarise(
        self,
        *,
        tender_id: int,
        coverage_items: list[ComplianceRequirementCoverage],
    ) -> dict[str, Any]:
        summary = {
            "total_requirements": len(coverage_items),
            "fully_covered": 0,
            "partially_covered": 0,
            "uncovered": 0,
            "high_priority_uncovered": 0,
        }
        by_domain: dict[str, dict[str, int]] = {}
        gaps: list[dict[str, Any]] = []

        for coverage in coverage_items:
            coverage_status = _coverage_status(coverage)
            summary[coverage_status] = summary.get(coverage_status, 0) + 1
            is_high = (coverage.priority or "medium").casefold() == "high"
            if coverage_status == "uncovered" and is_high:
                summary["high_priority_uncovered"] += 1

            tag = self._ontology.tag_text(
                coverage.requirement_text,
                category=coverage.category,
                priority=coverage.priority,
            )
            domain_key = tag.ontology_domain.value
            bucket = by_domain.setdefault(
                domain_key,
                {"domain": domain_key, "total": 0, "covered": 0, "partial": 0, "uncovered": 0},
            )
            bucket["total"] += 1
            if coverage_status == "fully_covered":
                bucket["covered"] += 1
            elif coverage_status == "partially_covered":
                bucket["partial"] += 1
            else:
                bucket["uncovered"] += 1

            if coverage_status != "fully_covered":
                gaps.append(
                    {
                        "requirement_id": coverage.id,
                        "summary": coverage.requirement_text,
                        "priority": coverage.priority or "medium",
                        "ontology_domain": domain_key,
                        "ontology_subdomain": tag.ontology_subdomain,
                        "mapped_section_id": coverage.proposal_section_id,
                        "mapped_section_title": coverage.proposal_section_title,
                        "coverage_status": coverage_status,
                        "coverage_source": coverage.coverage_source,
                    }
                )

        ordered_domains = sorted(
            by_domain.values(),
            key=lambda bucket: (-bucket["total"], bucket["domain"]),
        )
        gaps.sort(
            key=lambda gap: (
                0 if gap["priority"] == "high" else 1 if gap["priority"] == "medium" else 2,
                gap["requirement_id"],
            )
        )
        return {
            "tender_id": tender_id,
            "summary": summary,
            "by_domain": ordered_domains,
            "gaps": gaps,
        }


__all__ = ["CoverageAnalyzer"]
