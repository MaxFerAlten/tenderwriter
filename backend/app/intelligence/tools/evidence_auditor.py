"""EvidenceAuditor — classify evidence depth per requirement.

Wave-1 rules (no LLM):

* ``strong``   — requirement is mapped to a proposal section that is
  already APPROVED. The approved narrative is treated as documentary
  evidence.
* ``weak``     — requirement is mapped to a section but not yet approved,
  OR the consolidated requirement has citation metadata but no section
  mapping. There is a claim but no approved proof.
* ``missing``  — no mapping and no citation metadata at all.

The tool is read-only and never updates compliance gates or section
statuses. It just tags each requirement with its evidence class so the UI
and the downstream ``TenderIntelligenceAgent`` can reason about it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.intelligence.ontology import TenderOntologyService, default_ontology_service
from app.models import (
    ComplianceStatus,
    ConsolidatedRequirement,
    Proposal,
    SectionStatus,
    Tender,
    TenderRequirement,
)
from app.services.compliance_observability import build_compliance_requirement_coverage

_EVIDENCE_STATUSES = ("strong", "weak", "missing")


def _has_citation_metadata(consolidated: ConsolidatedRequirement) -> bool:
    metadata = consolidated.metadata_json or {}
    if not isinstance(metadata, Mapping):
        return False
    sources: Iterable[Any] = metadata.get("sources") or []
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        raw_candidate = source.get("raw_candidate")
        if isinstance(raw_candidate, Mapping) and raw_candidate.get("citations"):
            return True
        if source.get("citations"):
            return True
    return False


def _section_status_map(tender: Tender) -> dict[int, SectionStatus]:
    statuses: dict[int, SectionStatus] = {}
    for proposal in list(tender.proposals or []):
        for section in list(proposal.sections or []):
            if section.id is None:
                continue
            statuses[int(section.id)] = section.status
    return statuses


class EvidenceAuditor:
    """Wave-1 evidence depth classifier."""

    name = "evidence_auditor"
    description = (
        "Classifies evidence depth (strong/weak/missing) for each tender "
        "requirement based on proposal section status and citation metadata. "
        "Read-only."
    )
    input_keys = ("tender_id", "only_high_priority")

    def __init__(self, ontology_service: TenderOntologyService | None = None) -> None:
        self._ontology = ontology_service or default_ontology_service()

    async def run(
        self,
        db: AsyncSession,
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        tender_id = inputs.get("tender_id")
        if tender_id is None:
            raise ValueError("evidence_auditor requires 'tender_id'")
        only_high_priority = bool(inputs.get("only_high_priority") or False)
        tender = await self._load_tender(db, int(tender_id))
        if tender is None:
            return self._empty_result(int(tender_id), only_high_priority)

        return self._audit(
            tender_id=int(tender_id),
            tender=tender,
            only_high_priority=only_high_priority,
        )

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

    def _empty_result(self, tender_id: int, only_high_priority: bool) -> dict[str, Any]:
        return {
            "tender_id": tender_id,
            "only_high_priority": only_high_priority,
            "summary": {
                "requirements_checked": 0,
                "strong_evidence": 0,
                "weak_evidence": 0,
                "missing_evidence": 0,
            },
            "findings": [],
        }

    def _audit(
        self,
        *,
        tender_id: int,
        tender: Tender,
        only_high_priority: bool,
    ) -> dict[str, Any]:
        section_statuses = _section_status_map(tender)
        coverage_items = build_compliance_requirement_coverage(tender)

        consolidated_by_id = {
            int(requirement.id): requirement
            for requirement in list(tender.consolidated_requirements or [])
            if requirement.id is not None
        }

        summary = {
            "requirements_checked": 0,
            "strong_evidence": 0,
            "weak_evidence": 0,
            "missing_evidence": 0,
        }
        findings: list[dict[str, Any]] = []
        for coverage in coverage_items:
            priority = (coverage.priority or "medium").casefold()
            if only_high_priority and priority != "high":
                continue

            tag = self._ontology.tag_text(
                coverage.requirement_text,
                category=coverage.category,
                priority=coverage.priority,
            )

            section_status = (
                section_statuses.get(coverage.proposal_section_id)
                if coverage.proposal_section_id is not None
                else None
            )
            consolidated = (
                consolidated_by_id.get(coverage.id)
                if coverage.coverage_source.startswith("consolidated")
                else None
            )
            has_citation = bool(consolidated and _has_citation_metadata(consolidated))

            evidence_status = self._classify_evidence(
                compliance_status=coverage.compliance_status,
                section_status=section_status,
                has_mapped_section=coverage.proposal_section_id is not None,
                has_citation=has_citation,
            )

            summary["requirements_checked"] += 1
            summary[f"{evidence_status}_evidence"] += 1
            findings.append(
                {
                    "requirement_id": coverage.id,
                    "summary": coverage.requirement_text,
                    "priority": coverage.priority or "medium",
                    "evidence_status": evidence_status,
                    "expected_evidence_type": tag.evidence_type,
                    "owner_role": tag.owner_role,
                    "ontology_domain": tag.ontology_domain.value,
                    "ontology_subdomain": tag.ontology_subdomain,
                    "mapped_section_id": coverage.proposal_section_id,
                    "mapped_section_title": coverage.proposal_section_title,
                    "has_citation_metadata": has_citation,
                }
            )

        findings.sort(
            key=lambda item: (
                _EVIDENCE_STATUSES.index("missing")
                if item["evidence_status"] == "missing"
                else _EVIDENCE_STATUSES.index(item["evidence_status"]),
                0 if item["priority"] == "high" else 1 if item["priority"] == "medium" else 2,
                item["requirement_id"],
            )
        )
        return {
            "tender_id": tender_id,
            "only_high_priority": only_high_priority,
            "summary": summary,
            "findings": findings,
        }

    @staticmethod
    def _classify_evidence(
        *,
        compliance_status: ComplianceStatus,
        section_status: SectionStatus | None,
        has_mapped_section: bool,
        has_citation: bool,
    ) -> str:
        if (
            section_status == SectionStatus.APPROVED
            or compliance_status == ComplianceStatus.FULLY_ADDRESSED
        ):
            return "strong"
        if has_mapped_section or has_citation:
            return "weak"
        return "missing"


__all__ = ["EvidenceAuditor"]
