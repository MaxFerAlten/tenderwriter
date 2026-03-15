from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    ComplianceGate,
    ComplianceGateStatus,
    ComplianceStatus,
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

AUTO_COMPLIANCE_GATE_NAME = "Auto compliance readiness"
_AUTO_NOTES = {
    ComplianceGateStatus.OPEN: "Auto-managed gate: unresolved mapped requirements are still pending.",
    ComplianceGateStatus.PASSED: "Auto-managed gate: all mapped requirements are fully addressed.",
    ComplianceGateStatus.FAILED: "Auto-managed gate: tender deadline passed with unresolved requirements.",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def derive_requirement_compliance_status(section_status: SectionStatus | None) -> ComplianceStatus:
    if section_status == SectionStatus.APPROVED:
        return ComplianceStatus.FULLY_ADDRESSED
    if section_status in {SectionStatus.IN_PROGRESS, SectionStatus.IN_REVIEW}:
        return ComplianceStatus.PARTIALLY_ADDRESSED
    return ComplianceStatus.NOT_ADDRESSED


def determine_auto_gate_target_status(
    *,
    requirements: Sequence[TenderRequirement],
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
        status in {SectionStatus.IN_REVIEW, SectionStatus.APPROVED}
        for status in section_statuses
    )
    all_fully_addressed = all(status == ComplianceStatus.FULLY_ADDRESSED for status in requirement_statuses)

    if all_fully_addressed:
        return ComplianceGateStatus.PASSED

    if tender_due_at is not None:
        due_at = tender_due_at if tender_due_at.tzinfo else tender_due_at.replace(tzinfo=timezone.utc)
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
            selectinload(Tender.requirements),
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

    gate_target = determine_auto_gate_target_status(
        requirements=list(tender.requirements or []),
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
                "compliance_gate_passed" if gate_target == ComplianceGateStatus.PASSED else "compliance_gate_failed",
                build_compliance_gate_decision_event_payload(gate=gate),
            )
        )
        return events

    gate.decision_notes = _AUTO_NOTES[gate_target]
    if gate_target != ComplianceGateStatus.OPEN and gate.evaluated_at is None:
        gate.evaluated_at = now
    await db.flush()
    return events

