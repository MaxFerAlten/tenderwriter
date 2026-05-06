from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceGateStatus,
    ComplianceStatus,
    ConsolidatedRequirement,
    Proposal,
    ProposalSection,
    SectionStatus,
    Tender,
    TenderRequirement,
)
from app.services.kpi_reason_engine import (
    build_compliance_gate_decision_event_payload,
    build_compliance_gate_opened_event_payload,
)
from app.services.tender_requirements import normalize_requirement_text

AUTO_COMPLIANCE_GATE_NAME = "Auto compliance readiness"
_AUTO_NOTES = {
    ComplianceGateStatus.OPEN: "Auto-managed gate: unresolved mapped requirements are still pending.",
    ComplianceGateStatus.PASSED: "Auto-managed gate: all mapped requirements are fully addressed.",
    ComplianceGateStatus.FAILED: "Auto-managed gate: tender deadline passed with unresolved requirements.",
}


@dataclass
class ComplianceRequirementCoverage:
    id: int
    requirement_text: str
    category: str | None
    priority: str
    compliance_status: ComplianceStatus
    proposal_section_id: int | None = None
    proposal_section_title: str | None = None
    coverage_source: str = "legacy"


def _now_utc() -> datetime:
    return datetime.now(UTC)


def derive_requirement_compliance_status(section_status: SectionStatus | None) -> ComplianceStatus:
    if section_status == SectionStatus.APPROVED:
        return ComplianceStatus.FULLY_ADDRESSED
    if section_status in {SectionStatus.IN_PROGRESS, SectionStatus.IN_REVIEW}:
        return ComplianceStatus.PARTIALLY_ADDRESSED
    return ComplianceStatus.NOT_ADDRESSED


def _coerce_compliance_status(value: Any) -> ComplianceStatus:
    if isinstance(value, ComplianceStatus):
        return value
    try:
        return ComplianceStatus(str(value))
    except ValueError:
        return ComplianceStatus.NOT_ADDRESSED


def _source_payloads(metadata_json: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(metadata_json, Mapping):
        return []
    payloads: list[Mapping[str, Any]] = []
    primary_source = metadata_json.get("primary_source")
    if isinstance(primary_source, Mapping):
        payloads.append(primary_source)
    for source in metadata_json.get("sources") or []:
        if isinstance(source, Mapping):
            payloads.append(source)
    return payloads


def _legacy_requirement_for_consolidated(
    consolidated_requirement: ConsolidatedRequirement,
    *,
    legacy_by_id: Mapping[int, TenderRequirement],
    legacy_by_text: Mapping[str, TenderRequirement],
) -> TenderRequirement | None:
    for payload in _source_payloads(consolidated_requirement.metadata_json):
        legacy_id = payload.get("legacy_requirement_id")
        if legacy_id is None:
            continue
        try:
            legacy_requirement = legacy_by_id.get(int(legacy_id))
        except (TypeError, ValueError):
            legacy_requirement = None
        if legacy_requirement is not None:
            return legacy_requirement

    normalized_text = normalize_requirement_text(
        consolidated_requirement.normalized_text or consolidated_requirement.canonical_text or ""
    )
    if normalized_text:
        return legacy_by_text.get(normalized_text)
    return None


def _legacy_requirement_to_coverage(
    requirement: TenderRequirement,
) -> ComplianceRequirementCoverage:
    mapped_section = requirement.proposal_section
    return ComplianceRequirementCoverage(
        id=int(requirement.id or 0),
        requirement_text=str(requirement.requirement_text or ""),
        category=requirement.category,
        priority=str(requirement.priority or "medium"),
        compliance_status=_coerce_compliance_status(requirement.compliance_status),
        proposal_section_id=requirement.proposal_section_id,
        proposal_section_title=mapped_section.title if mapped_section else None,
        coverage_source="legacy",
    )


def _consolidated_requirement_to_coverage(
    requirement: ConsolidatedRequirement,
    *,
    legacy_requirement: TenderRequirement | None,
) -> ComplianceRequirementCoverage:
    is_approved = str(requirement.review_state or "pending").casefold() == "approved"
    mapped_section = legacy_requirement.proposal_section if legacy_requirement is not None else None
    return ComplianceRequirementCoverage(
        id=int(requirement.id or 0),
        requirement_text=str(requirement.canonical_text or ""),
        category=requirement.category
        or (legacy_requirement.category if legacy_requirement else None),
        priority=str(
            requirement.priority
            or (legacy_requirement.priority if legacy_requirement else "medium")
        ),
        compliance_status=_coerce_compliance_status(
            legacy_requirement.compliance_status
            if is_approved and legacy_requirement is not None
            else None
        ),
        proposal_section_id=(
            legacy_requirement.proposal_section_id
            if is_approved and legacy_requirement is not None
            else None
        ),
        proposal_section_title=mapped_section.title if is_approved and mapped_section else None,
        coverage_source="consolidated_approved" if is_approved else "consolidated_review_pending",
    )


def build_compliance_requirement_coverage(tender: Tender) -> list[ComplianceRequirementCoverage]:
    """Build the compliance coverage source, preferring approved consolidated requirements."""

    legacy_requirements = list(tender.requirements or [])
    legacy_by_id = {
        int(requirement.id): requirement
        for requirement in legacy_requirements
        if requirement.id is not None
    }
    legacy_by_text = {
        normalize_requirement_text(requirement.requirement_text or ""): requirement
        for requirement in legacy_requirements
        if requirement.requirement_text
    }

    active_consolidated = [
        requirement
        for requirement in list(tender.consolidated_requirements or [])
        if str(requirement.graph_state or "active").casefold() == "active"
    ]
    has_approved_consolidated = any(
        str(requirement.review_state or "pending").casefold() == "approved"
        for requirement in active_consolidated
    )

    if not has_approved_consolidated:
        return [_legacy_requirement_to_coverage(requirement) for requirement in legacy_requirements]

    coverage_items = []
    for requirement in sorted(
        active_consolidated,
        key=lambda item: (str(item.priority or "medium").casefold(), item.id or 0),
    ):
        legacy_requirement = _legacy_requirement_for_consolidated(
            requirement,
            legacy_by_id=legacy_by_id,
            legacy_by_text=legacy_by_text,
        )
        coverage_items.append(
            _consolidated_requirement_to_coverage(
                requirement,
                legacy_requirement=legacy_requirement,
            )
        )
    return coverage_items


def determine_auto_gate_target_status(
    *,
    requirements: Sequence[TenderRequirement | ComplianceRequirementCoverage],
    sections: Sequence[ProposalSection],
    tender_due_at: datetime | None,
    now: datetime | None = None,
) -> ComplianceGateStatus | None:
    if not requirements:
        return None

    now = now or _now_utc()
    requirement_statuses = [requirement.compliance_status for requirement in requirements]
    section_statuses = [section.status for section in sections if section.status is not None]
    any_progress = any(
        status in {ComplianceStatus.PARTIALLY_ADDRESSED, ComplianceStatus.FULLY_ADDRESSED}
        for status in requirement_statuses
    )
    review_or_completion_started = any(
        status in {SectionStatus.IN_REVIEW, SectionStatus.APPROVED} for status in section_statuses
    )
    all_fully_addressed = all(
        status == ComplianceStatus.FULLY_ADDRESSED for status in requirement_statuses
    )

    if all_fully_addressed:
        return ComplianceGateStatus.PASSED

    if tender_due_at is not None:
        due_at = tender_due_at if tender_due_at.tzinfo else tender_due_at.replace(tzinfo=UTC)
        if due_at <= now and (review_or_completion_started or any_progress):
            return ComplianceGateStatus.FAILED

    if review_or_completion_started or (any_progress and not sections):
        return ComplianceGateStatus.OPEN

    return None


async def _load_tender_for_compliance(db: AsyncSession, tender_id: int) -> Tender | None:
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


async def _load_auto_gate(db: AsyncSession, tender_id: int) -> ComplianceGate | None:
    result = await db.execute(
        select(ComplianceGate)
        .where(
            ComplianceGate.tender_id == tender_id,
            ComplianceGate.gate_name == AUTO_COMPLIANCE_GATE_NAME,
        )
        .order_by(ComplianceGate.id.desc())
    )
    return result.scalars().first()


def _collect_sections(tender: Tender) -> list[ProposalSection]:
    sections: list[ProposalSection] = []
    for proposal in list(tender.proposals or []):
        sections.extend(list(proposal.sections or []))
    return sections


async def sync_requirement_compliance_and_gate(
    db: AsyncSession,
    *,
    tender_id: int,
    actor_id: int | None,
) -> list[tuple[str, dict]]:
    tender = await _load_tender_for_compliance(db, tender_id)
    if tender is None:
        return []

    sections = _collect_sections(tender)
    section_by_id = {section.id: section for section in sections if section.id is not None}
    for requirement in list(tender.requirements or []):
        if requirement.proposal_section_id is None:
            continue
        section = section_by_id.get(requirement.proposal_section_id)
        if section is None:
            continue
        requirement.compliance_status = derive_requirement_compliance_status(section.status)

    coverage_requirements = build_compliance_requirement_coverage(tender)
    gate_target = determine_auto_gate_target_status(
        requirements=coverage_requirements,
        sections=sections,
        tender_due_at=tender.deadline,
    )
    if gate_target is None:
        await db.flush()
        return []

    gate = await _load_auto_gate(db, tender_id)
    events: list[tuple[str, dict]] = []
    now = _now_utc()

    if gate is None:
        gate = ComplianceGate(
            tender_id=tender.id,
            contribution_unit_id=None,
            owner_user_id=actor_id,
            gate_name=AUTO_COMPLIANCE_GATE_NAME,
            due_at=tender.deadline,
            decision_notes=_AUTO_NOTES[ComplianceGateStatus.OPEN],
            status=ComplianceGateStatus.OPEN,
        )
        db.add(gate)
        await db.flush()
        events.append(
            (
                "compliance_gate_opened",
                build_compliance_gate_opened_event_payload(gate=gate),
            )
        )

    gate.due_at = tender.deadline

    if gate_target == ComplianceGateStatus.OPEN:
        if gate.status != ComplianceGateStatus.OPEN:
            gate.status = ComplianceGateStatus.OPEN
            gate.evaluated_at = None
            gate.decision_notes = _AUTO_NOTES[ComplianceGateStatus.OPEN]
            await db.flush()
            events.append(
                (
                    "compliance_gate_opened",
                    build_compliance_gate_opened_event_payload(gate=gate),
                )
            )
        else:
            gate.decision_notes = _AUTO_NOTES[ComplianceGateStatus.OPEN]
            await db.flush()
        return events

    if gate.status != gate_target:
        gate.status = gate_target
        gate.evaluated_at = now
        gate.decision_notes = _AUTO_NOTES[gate_target]
        await db.flush()
        events.append(
            (
                "compliance_gate_passed"
                if gate_target == ComplianceGateStatus.PASSED
                else "compliance_gate_failed",
                build_compliance_gate_decision_event_payload(gate=gate),
            )
        )
        return events

    gate.decision_notes = _AUTO_NOTES[gate_target]
    if gate_target != ComplianceGateStatus.OPEN and gate.evaluated_at is None:
        gate.evaluated_at = now
    await db.flush()
    return events
