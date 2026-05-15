from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.lifecycle_projector import project_workflow_events
from app.models import (
    ContributionRequest,
    ContributionRequestStatus,
    ContributionUnit,
    ContributionUnitStatus,
    ProposalSection,
    ReviewCycle,
    ReviewCycleStatus,
    ReworkAction,
    ReworkStatus,
    SectionStatus,
)
from app.services.kpi_reason_engine import (
    build_contribution_assignment_confirmed_event_payload,
    build_contribution_due_date_set_event_payload,
    build_contribution_received_event_payload,
    build_contribution_request_created_event_payload,
    build_contribution_review_completed_event_payload,
    build_review_cycle_started_event_payload,
    build_rework_requested_event_payload,
    build_rework_resolved_event_payload,
)


@dataclass(slots=True)
class SectionTransitionPlan:
    cancel_open_requests: bool = False
    ensure_request: bool = False
    mark_request_received: bool = False
    start_review: bool = False
    complete_review: bool = False
    review_outcome: str | None = None
    open_rework: bool = False
    resolve_rework: bool = False


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def derive_contribution_status(
    *,
    section_status: SectionStatus,
    assigned_to: int | None,
    has_open_rework: bool,
) -> ContributionUnitStatus:
    if has_open_rework:
        return ContributionUnitStatus.REWORK
    if section_status == SectionStatus.APPROVED:
        return ContributionUnitStatus.COMPLETED
    if section_status == SectionStatus.IN_REVIEW:
        return ContributionUnitStatus.IN_REVIEW
    if section_status == SectionStatus.IN_PROGRESS:
        return (
            ContributionUnitStatus.RECEIVED
            if assigned_to is not None
            else ContributionUnitStatus.REQUESTED
        )
    if assigned_to is not None:
        return ContributionUnitStatus.REQUESTED
    return ContributionUnitStatus.OPEN


def build_section_transition_plan(
    *,
    previous_status: SectionStatus,
    new_status: SectionStatus,
    previous_assigned_to: int | None,
    new_assigned_to: int | None,
) -> SectionTransitionPlan:
    plan = SectionTransitionPlan()
    assignment_changed = previous_assigned_to != new_assigned_to

    if assignment_changed:
        plan.cancel_open_requests = True
    if (
        assignment_changed
        and new_assigned_to is not None
        and new_status in {SectionStatus.TODO, SectionStatus.IN_PROGRESS}
    ):
        plan.ensure_request = True

    if new_status == SectionStatus.IN_REVIEW and previous_status != SectionStatus.IN_REVIEW:
        plan.mark_request_received = True
        plan.start_review = True
        plan.resolve_rework = True

    if new_status == SectionStatus.APPROVED and previous_status != SectionStatus.APPROVED:
        plan.mark_request_received = True
        plan.resolve_rework = True
        if previous_status == SectionStatus.IN_REVIEW:
            plan.complete_review = True
            plan.review_outcome = "approved"
    elif previous_status == SectionStatus.IN_REVIEW and new_status == SectionStatus.IN_PROGRESS:
        plan.complete_review = True
        plan.review_outcome = "changes_requested"
        plan.open_rework = True

    return plan


async def _load_contribution(
    db: AsyncSession,
    *,
    tender_id: int,
    section_id: int,
) -> ContributionUnit | None:
    result = await db.execute(
        select(ContributionUnit).where(
            ContributionUnit.tender_id == tender_id,
            ContributionUnit.proposal_section_id == section_id,
        )
    )
    return result.scalar_one_or_none()


async def ensure_contribution_for_section(
    db: AsyncSession,
    *,
    tender_id: int,
    section: ProposalSection,
    actor_id: int | None,
) -> ContributionUnit:
    contribution = await _load_contribution(db, tender_id=tender_id, section_id=section.id)
    if contribution is None:
        contribution = ContributionUnit(
            tender_id=tender_id,
            proposal_section_id=section.id,
            owner_user_id=section.assigned_to,
            title=section.title,
            description="Auto-managed from proposal section workflow.",
            status=derive_contribution_status(
                section_status=section.status or SectionStatus.TODO,
                assigned_to=section.assigned_to,
                has_open_rework=False,
            ),
            created_by=actor_id,
        )
        db.add(contribution)
        await db.flush()
        return contribution

    contribution.title = section.title
    contribution.owner_user_id = section.assigned_to
    return contribution


async def _load_open_requests(
    db: AsyncSession, *, contribution_id: int
) -> list[ContributionRequest]:
    result = await db.execute(
        select(ContributionRequest)
        .where(
            ContributionRequest.contribution_unit_id == contribution_id,
            ContributionRequest.status == ContributionRequestStatus.OPEN,
        )
        .order_by(ContributionRequest.id.desc())
    )
    return list(result.scalars().all())


async def _load_latest_open_review(db: AsyncSession, *, contribution_id: int) -> ReviewCycle | None:
    result = await db.execute(
        select(ReviewCycle)
        .where(
            ReviewCycle.contribution_unit_id == contribution_id,
            ReviewCycle.status == ReviewCycleStatus.OPEN,
        )
        .order_by(ReviewCycle.id.desc())
    )
    return result.scalars().first()


async def _load_open_reworks(db: AsyncSession, *, contribution_id: int) -> list[ReworkAction]:
    result = await db.execute(
        select(ReworkAction)
        .where(
            ReworkAction.contribution_unit_id == contribution_id,
            ReworkAction.status == ReworkStatus.OPEN,
        )
        .order_by(ReworkAction.id.desc())
    )
    return list(result.scalars().all())


async def _cancel_open_requests(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    keep_user_id: int | None,
) -> None:
    for request_row in await _load_open_requests(db, contribution_id=contribution.id):
        if keep_user_id is not None and request_row.requested_to_user_id == keep_user_id:
            continue
        request_row.status = ContributionRequestStatus.CANCELLED


async def _ensure_request_for_assignment(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    assigned_to: int,
    actor_id: int | None,
    occurred_at: datetime,
) -> list[tuple[str, dict]]:
    await _cancel_open_requests(db, contribution=contribution, keep_user_id=assigned_to)
    for request_row in await _load_open_requests(db, contribution_id=contribution.id):
        if request_row.requested_to_user_id == assigned_to:
            contribution.status = ContributionUnitStatus.REQUESTED
            return []

    request_row = ContributionRequest(
        contribution_unit_id=contribution.id,
        requested_by=actor_id,
        requested_to_user_id=assigned_to,
        request_channel="proposal_assignment",
        requested_at=occurred_at,
        due_at=contribution.due_at,
        status=ContributionRequestStatus.OPEN,
    )
    db.add(request_row)
    await db.flush()

    contribution.status = ContributionUnitStatus.REQUESTED
    events = [
        (
            "contribution_request_created",
            build_contribution_request_created_event_payload(
                request=request_row, contribution=contribution
            ),
        )
    ]
    events.append(
        (
            "contribution_assignment_confirmed",
            build_contribution_assignment_confirmed_event_payload(
                occurred_at=occurred_at,
                external_contribution_id=str(contribution.id),
                owner_user_id=assigned_to,
                external_request_id=str(request_row.id),
                notes="Assignment captured from proposal section workflow.",
            ),
        )
    )
    if request_row.due_at is not None:
        events.append(
            (
                "contribution_due_date_set",
                build_contribution_due_date_set_event_payload(
                    request=request_row, contribution=contribution
                ),
            )
        )
    return events


async def _mark_latest_request_received(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    occurred_at: datetime,
) -> list[tuple[str, dict]]:
    for request_row in await _load_open_requests(db, contribution_id=contribution.id):
        request_row.response_received_at = request_row.response_received_at or occurred_at
        request_row.response_summary = (
            request_row.response_summary or "Auto-received from proposal section workflow."
        )
        request_row.status = ContributionRequestStatus.RECEIVED
        contribution.status = ContributionUnitStatus.RECEIVED
        await db.flush()
        return [
            (
                "contribution_received",
                build_contribution_received_event_payload(
                    request=request_row, contribution=contribution
                ),
            )
        ]
    return []


async def _ensure_open_review(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    actor_id: int | None,
    occurred_at: datetime,
) -> tuple[ReviewCycle, bool]:
    review = await _load_latest_open_review(db, contribution_id=contribution.id)
    if review is not None:
        contribution.status = ContributionUnitStatus.IN_REVIEW
        return review, False

    review = ReviewCycle(
        contribution_unit_id=contribution.id,
        reviewer_id=actor_id,
        stage_name="proposal_section_review",
        started_at=occurred_at,
        notes="Auto-started from proposal section workflow.",
        status=ReviewCycleStatus.OPEN,
    )
    db.add(review)
    await db.flush()
    contribution.status = ContributionUnitStatus.IN_REVIEW
    return review, True


async def _complete_review(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    actor_id: int | None,
    occurred_at: datetime,
    outcome: str,
) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    review, created = await _ensure_open_review(
        db,
        contribution=contribution,
        actor_id=actor_id,
        occurred_at=occurred_at,
    )
    if created:
        events.append(
            (
                "contribution_review_started",
                build_review_cycle_started_event_payload(review=review, contribution=contribution),
            )
        )

    review.completed_at = occurred_at
    review.outcome = outcome
    review.status = ReviewCycleStatus.COMPLETED
    if outcome == "approved":
        review.notes = review.notes or "Automatically approved from proposal workflow."
        contribution.status = ContributionUnitStatus.COMPLETED
    else:
        review.notes = review.notes or "Changes requested from proposal workflow."
    await db.flush()
    review_payload = build_contribution_review_completed_event_payload(
        review=review, contribution=contribution
    )
    events.append(
        (
            "review_approved" if outcome == "approved" else "review_changes_requested",
            review_payload,
        )
    )
    return events


async def _resolve_open_reworks(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    occurred_at: datetime,
) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for rework in await _load_open_reworks(db, contribution_id=contribution.id):
        rework.resolved_at = rework.resolved_at or occurred_at
        rework.resolution_notes = (
            rework.resolution_notes or "Auto-resolved from proposal section workflow."
        )
        rework.status = ReworkStatus.RESOLVED
        events.append(
            (
                "rework_resolved",
                build_rework_resolved_event_payload(rework=rework, contribution=contribution),
            )
        )
    await db.flush()
    return events


async def _ensure_open_rework(
    db: AsyncSession,
    *,
    contribution: ContributionUnit,
    actor_id: int | None,
    occurred_at: datetime,
) -> list[tuple[str, dict]]:
    existing = await _load_open_reworks(db, contribution_id=contribution.id)
    if existing:
        contribution.status = ContributionUnitStatus.REWORK
        return []

    latest_review_result = await db.execute(
        select(ReviewCycle)
        .where(ReviewCycle.contribution_unit_id == contribution.id)
        .order_by(ReviewCycle.id.desc())
    )
    latest_review = latest_review_result.scalars().first()
    rework = ReworkAction(
        contribution_unit_id=contribution.id,
        review_cycle_id=latest_review.id if latest_review is not None else None,
        requested_by=actor_id,
        assigned_to_user_id=contribution.owner_user_id,
        severity="medium",
        is_blocking=True,
        reason="Auto-created from proposal section leaving review.",
        requested_at=occurred_at,
        status=ReworkStatus.OPEN,
    )
    db.add(rework)
    await db.flush()
    contribution.status = ContributionUnitStatus.REWORK
    return [
        (
            "rework_requested",
            build_rework_requested_event_payload(rework=rework, contribution=contribution),
        )
    ]


async def sync_section_operational_workflow(
    db: AsyncSession,
    *,
    tender_id: int,
    section: ProposalSection,
    actor_id: int | None,
    previous_status: SectionStatus,
    previous_assigned_to: int | None,
) -> list[tuple[str, dict]]:
    contribution = await ensure_contribution_for_section(
        db,
        tender_id=tender_id,
        section=section,
        actor_id=actor_id,
    )
    plan = build_section_transition_plan(
        previous_status=previous_status,
        new_status=section.status or SectionStatus.TODO,
        previous_assigned_to=previous_assigned_to,
        new_assigned_to=section.assigned_to,
    )
    occurred_at = _now_utc()
    events: list[tuple[str, dict]] = []

    if plan.cancel_open_requests and section.assigned_to != previous_assigned_to:
        await _cancel_open_requests(
            db,
            contribution=contribution,
            keep_user_id=section.assigned_to,
        )

    if plan.ensure_request and section.assigned_to is not None:
        events.extend(
            await _ensure_request_for_assignment(
                db,
                contribution=contribution,
                assigned_to=section.assigned_to,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
        )

    if plan.mark_request_received:
        events.extend(
            await _mark_latest_request_received(
                db,
                contribution=contribution,
                occurred_at=occurred_at,
            )
        )

    if plan.resolve_rework:
        events.extend(
            await _resolve_open_reworks(
                db,
                contribution=contribution,
                occurred_at=occurred_at,
            )
        )

    if plan.start_review:
        review, created = await _ensure_open_review(
            db,
            contribution=contribution,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )
        if created:
            events.append(
                (
                    "contribution_review_started",
                    build_review_cycle_started_event_payload(
                        review=review, contribution=contribution
                    ),
                )
            )

    if plan.complete_review and plan.review_outcome:
        events.extend(
            await _complete_review(
                db,
                contribution=contribution,
                actor_id=actor_id,
                occurred_at=occurred_at,
                outcome=plan.review_outcome,
            )
        )

    if plan.open_rework:
        events.extend(
            await _ensure_open_rework(
                db,
                contribution=contribution,
                actor_id=actor_id,
                occurred_at=occurred_at,
            )
        )

    contribution.status = derive_contribution_status(
        section_status=section.status or SectionStatus.TODO,
        assigned_to=section.assigned_to,
        has_open_rework=bool(await _load_open_reworks(db, contribution_id=contribution.id)),
    )
    await db.flush()

    if events:
        await project_workflow_events(
            db=db,
            rag_engine=None,
            tender_id=tender_id,
            contribution=contribution,
            events=events,
            actor_id=actor_id,
        )

    return events
