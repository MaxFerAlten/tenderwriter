from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.api.tenders import check_tender_access
from app.db.database import get_db
from app.models import (
    AttendanceRecord,
    AttendanceStatus,
    CallSession,
    CallSessionStatus,
    ComplianceGate,
    ComplianceGateStatus,
    ContributionRequest,
    ContributionRequestStatus,
    ContributionUnit,
    ContributionUnitStatus,
    ReworkAction,
    ReworkStatus,
    ReviewCycle,
    ReviewCycleStatus,
)
from app.services.kpi_reason_engine import (
    build_call_attendance_recorded_event_payload,
    build_call_scheduled_event_payload,
    build_compliance_gate_decision_event_payload,
    build_compliance_gate_opened_event_payload,
    build_contribution_due_date_set_event_payload,
    build_contribution_received_event_payload,
    build_contribution_request_created_event_payload,
    build_contribution_review_completed_event_payload,
    build_review_cycle_started_event_payload,
    build_rework_requested_event_payload,
    build_rework_resolved_event_payload,
    publish_domain_event,
    publish_tender_sync,
)

router = APIRouter()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


async def _publish_operational_events(
    db: AsyncSession,
    *,
    tender_id: int,
    actor_id: int | None,
    events: list[tuple[str, dict]],
) -> None:
    await publish_tender_sync(db, tender_id=tender_id, actor_id=actor_id)
    for event_type, payload in events:
        await publish_domain_event(
            db,
            tender_id=tender_id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload,
        )


async def _load_contribution_or_404(
    db: AsyncSession,
    *,
    tender_id: int,
    contribution_id: int,
) -> ContributionUnit:
    result = await db.execute(
        select(ContributionUnit).where(
            ContributionUnit.id == contribution_id,
            ContributionUnit.tender_id == tender_id,
        )
    )
    contribution = result.scalar_one_or_none()
    if contribution is None:
        raise HTTPException(status_code=404, detail="Contribution unit not found")
    return contribution


async def _load_request_or_404(
    db: AsyncSession,
    *,
    contribution_id: int,
    request_id: int,
) -> ContributionRequest:
    result = await db.execute(
        select(ContributionRequest).where(
            ContributionRequest.id == request_id,
            ContributionRequest.contribution_unit_id == contribution_id,
        )
    )
    request_row = result.scalar_one_or_none()
    if request_row is None:
        raise HTTPException(status_code=404, detail="Contribution request not found")
    return request_row


async def _load_review_or_404(
    db: AsyncSession,
    *,
    contribution_id: int,
    review_id: int,
) -> ReviewCycle:
    result = await db.execute(
        select(ReviewCycle).where(
            ReviewCycle.id == review_id,
            ReviewCycle.contribution_unit_id == contribution_id,
        )
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="Review cycle not found")
    return review


async def _load_rework_or_404(
    db: AsyncSession,
    *,
    contribution_id: int,
    rework_id: int,
) -> ReworkAction:
    result = await db.execute(
        select(ReworkAction).where(
            ReworkAction.id == rework_id,
            ReworkAction.contribution_unit_id == contribution_id,
        )
    )
    rework = result.scalar_one_or_none()
    if rework is None:
        raise HTTPException(status_code=404, detail="Rework action not found")
    return rework


async def _load_gate_or_404(db: AsyncSession, *, tender_id: int, gate_id: int) -> ComplianceGate:
    result = await db.execute(
        select(ComplianceGate).where(
            ComplianceGate.id == gate_id,
            ComplianceGate.tender_id == tender_id,
        )
    )
    gate = result.scalar_one_or_none()
    if gate is None:
        raise HTTPException(status_code=404, detail="Compliance gate not found")
    return gate


async def _load_call_or_404(db: AsyncSession, *, tender_id: int, call_id: int) -> CallSession:
    result = await db.execute(
        select(CallSession).where(
            CallSession.id == call_id,
            CallSession.tender_id == tender_id,
        )
    )
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call session not found")
    return call


class ContributionUnitCreate(BaseModel):
    title: str
    description: str | None = None
    department_name: str | None = None
    owner_user_id: int | None = None
    proposal_section_id: int | None = None
    due_at: datetime | None = None


class ContributionUnitResponse(BaseModel):
    id: int
    tender_id: int
    title: str
    description: str | None
    department_name: str | None
    owner_user_id: int | None
    proposal_section_id: int | None
    due_at: datetime | None
    status: str

    model_config = {"from_attributes": True}


class ContributionRequestCreate(BaseModel):
    requested_to_user_id: int | None = None
    requested_to_label: str | None = None
    request_channel: str | None = None
    requested_at: datetime | None = None
    due_at: datetime | None = None
    sla_target_hours: int | None = None
    sla_max_hours: int | None = None
    response_summary: str | None = None


class ContributionRequestReceive(BaseModel):
    response_received_at: datetime | None = None
    response_summary: str | None = None


class ContributionRequestResponse(BaseModel):
    id: int
    contribution_unit_id: int
    requested_to_user_id: int | None
    requested_to_label: str | None
    request_channel: str | None
    requested_at: datetime | None
    due_at: datetime | None
    sla_target_hours: int | None
    sla_max_hours: int | None
    response_received_at: datetime | None
    response_summary: str | None
    status: str

    model_config = {"from_attributes": True}


class ReviewCycleCreate(BaseModel):
    reviewer_id: int | None = None
    stage_name: str = "quality_review"
    started_at: datetime | None = None
    notes: str | None = None


class ReviewCycleComplete(BaseModel):
    completed_at: datetime | None = None
    outcome: str | None = None
    notes: str | None = None


class ReviewCycleResponse(BaseModel):
    id: int
    contribution_unit_id: int
    reviewer_id: int | None
    stage_name: str
    started_at: datetime | None
    completed_at: datetime | None
    outcome: str | None
    notes: str | None
    status: str

    model_config = {"from_attributes": True}


class ReworkCreate(BaseModel):
    review_cycle_id: int | None = None
    assigned_to_user_id: int | None = None
    severity: str = "medium"
    is_blocking: bool = True
    reason: str | None = None
    due_at: datetime | None = None
    requested_at: datetime | None = None


class ReworkResolve(BaseModel):
    resolved_at: datetime | None = None
    resolution_notes: str | None = None


class ReworkResponse(BaseModel):
    id: int
    contribution_unit_id: int
    review_cycle_id: int | None
    assigned_to_user_id: int | None
    severity: str
    is_blocking: bool
    reason: str | None
    due_at: datetime | None
    requested_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    status: str

    model_config = {"from_attributes": True}


class ComplianceGateCreate(BaseModel):
    gate_name: str
    contribution_unit_id: int | None = None
    owner_user_id: int | None = None
    due_at: datetime | None = None
    decision_notes: str | None = None


class ComplianceGateDecision(BaseModel):
    status: ComplianceGateStatus
    evaluated_at: datetime | None = None
    decision_notes: str | None = None


class ComplianceGateResponse(BaseModel):
    id: int
    tender_id: int
    contribution_unit_id: int | None
    owner_user_id: int | None
    gate_name: str
    due_at: datetime | None
    evaluated_at: datetime | None
    decision_notes: str | None
    status: str

    model_config = {"from_attributes": True}


class CallSessionCreate(BaseModel):
    title: str
    scheduled_at: datetime


class AttendanceRecordUpsert(BaseModel):
    user_id: int | None = None
    attendee_label: str | None = None
    attendance_status: AttendanceStatus = AttendanceStatus.INVITED
    recorded_at: datetime | None = None
    notes: str | None = None


class CallSessionResponse(BaseModel):
    id: int
    tender_id: int
    title: str
    scheduled_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    status: str

    model_config = {"from_attributes": True}


class AttendanceRecordResponse(BaseModel):
    id: int
    call_session_id: int
    user_id: int | None
    attendee_label: str | None
    attendance_status: str
    recorded_at: datetime | None
    notes: str | None

    model_config = {"from_attributes": True}


class OperationalSummaryResponse(BaseModel):
    tender_id: int
    contribution_count: int
    request_count: int
    open_rework_count: int
    open_gate_count: int
    call_count: int


@router.get("/{tender_id}/observability/summary", response_model=OperationalSummaryResponse)
async def get_operational_summary(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OperationalSummaryResponse:
    await check_tender_access(tender_id, current_user, db)

    contribution_count = len((await db.execute(select(ContributionUnit.id).where(ContributionUnit.tender_id == tender_id))).all())
    request_count = len(
        (
            await db.execute(
                select(ContributionRequest.id)
                .join(ContributionUnit, ContributionUnit.id == ContributionRequest.contribution_unit_id)
                .where(ContributionUnit.tender_id == tender_id)
            )
        ).all()
    )
    open_rework_count = len(
        (
            await db.execute(
                select(ReworkAction.id)
                .join(ContributionUnit, ContributionUnit.id == ReworkAction.contribution_unit_id)
                .where(
                    ContributionUnit.tender_id == tender_id,
                    ReworkAction.status == ReworkStatus.OPEN,
                )
            )
        ).all()
    )
    open_gate_count = len(
        (
            await db.execute(
                select(ComplianceGate.id).where(
                    ComplianceGate.tender_id == tender_id,
                    ComplianceGate.status == ComplianceGateStatus.OPEN,
                )
            )
        ).all()
    )
    call_count = len((await db.execute(select(CallSession.id).where(CallSession.tender_id == tender_id))).all())
    return OperationalSummaryResponse(
        tender_id=tender_id,
        contribution_count=contribution_count,
        request_count=request_count,
        open_rework_count=open_rework_count,
        open_gate_count=open_gate_count,
        call_count=call_count,
    )


@router.get("/{tender_id}/observability/contributions", response_model=list[ContributionUnitResponse])
async def list_contributions(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContributionUnitResponse]:
    await check_tender_access(tender_id, current_user, db)
    result = await db.execute(
        select(ContributionUnit)
        .where(ContributionUnit.tender_id == tender_id)
        .order_by(ContributionUnit.created_at.desc(), ContributionUnit.id.desc())
    )
    return [
        ContributionUnitResponse(
            id=item.id,
            tender_id=item.tender_id,
            title=item.title,
            description=item.description,
            department_name=item.department_name,
            owner_user_id=item.owner_user_id,
            proposal_section_id=item.proposal_section_id,
            due_at=item.due_at,
            status=str(_enum_value(item.status)),
        )
        for item in result.scalars().all()
    ]


@router.post("/{tender_id}/observability/contributions", response_model=ContributionUnitResponse, status_code=201)
async def create_contribution(
    tender_id: int,
    data: ContributionUnitCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContributionUnitResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = ContributionUnit(
        tender_id=tender_id,
        proposal_section_id=data.proposal_section_id,
        owner_user_id=data.owner_user_id,
        department_name=data.department_name,
        title=data.title,
        description=data.description,
        due_at=data.due_at,
        status=ContributionUnitStatus.OPEN,
        created_by=current_user.id,
    )
    db.add(contribution)
    await db.flush()
    await db.refresh(contribution)
    return ContributionUnitResponse(
        id=contribution.id,
        tender_id=contribution.tender_id,
        title=contribution.title,
        description=contribution.description,
        department_name=contribution.department_name,
        owner_user_id=contribution.owner_user_id,
        proposal_section_id=contribution.proposal_section_id,
        due_at=contribution.due_at,
        status=str(_enum_value(contribution.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/requests", response_model=ContributionRequestResponse, status_code=201)
async def create_contribution_request(
    tender_id: int,
    contribution_id: int,
    data: ContributionRequestCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContributionRequestResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    request_row = ContributionRequest(
        contribution_unit_id=contribution.id,
        requested_by=current_user.id,
        requested_to_user_id=data.requested_to_user_id,
        requested_to_label=data.requested_to_label,
        request_channel=data.request_channel,
        requested_at=data.requested_at or _now_utc(),
        due_at=data.due_at,
        sla_target_hours=data.sla_target_hours,
        sla_max_hours=data.sla_max_hours,
        response_summary=data.response_summary,
        status=ContributionRequestStatus.OPEN,
    )
    contribution.status = ContributionUnitStatus.REQUESTED
    if data.due_at is not None and contribution.due_at is None:
        contribution.due_at = data.due_at
    db.add(request_row)
    await db.flush()
    await db.refresh(request_row)

    events: list[tuple[str, dict]] = [
        (
            "contribution_request_created",
            build_contribution_request_created_event_payload(request=request_row, contribution=contribution),
        )
    ]
    if request_row.due_at is not None:
        events.append(
            (
                "contribution_due_date_set",
                build_contribution_due_date_set_event_payload(request=request_row, contribution=contribution),
            )
        )
    await _publish_operational_events(db, tender_id=tender_id, actor_id=current_user.id, events=events)

    return ContributionRequestResponse(
        id=request_row.id,
        contribution_unit_id=request_row.contribution_unit_id,
        requested_to_user_id=request_row.requested_to_user_id,
        requested_to_label=request_row.requested_to_label,
        request_channel=request_row.request_channel,
        requested_at=request_row.requested_at,
        due_at=request_row.due_at,
        sla_target_hours=request_row.sla_target_hours,
        sla_max_hours=request_row.sla_max_hours,
        response_received_at=request_row.response_received_at,
        response_summary=request_row.response_summary,
        status=str(_enum_value(request_row.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/requests/{request_id}/receive", response_model=ContributionRequestResponse)
async def receive_contribution_request(
    tender_id: int,
    contribution_id: int,
    request_id: int,
    data: ContributionRequestReceive,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContributionRequestResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    request_row = await _load_request_or_404(db, contribution_id=contribution.id, request_id=request_id)

    request_row.response_received_at = data.response_received_at or _now_utc()
    if data.response_summary is not None:
        request_row.response_summary = data.response_summary
    request_row.status = ContributionRequestStatus.RECEIVED
    contribution.status = ContributionUnitStatus.RECEIVED
    await db.flush()
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "contribution_received",
                build_contribution_received_event_payload(request=request_row, contribution=contribution),
            )
        ],
    )

    return ContributionRequestResponse(
        id=request_row.id,
        contribution_unit_id=request_row.contribution_unit_id,
        requested_to_user_id=request_row.requested_to_user_id,
        requested_to_label=request_row.requested_to_label,
        request_channel=request_row.request_channel,
        requested_at=request_row.requested_at,
        due_at=request_row.due_at,
        sla_target_hours=request_row.sla_target_hours,
        sla_max_hours=request_row.sla_max_hours,
        response_received_at=request_row.response_received_at,
        response_summary=request_row.response_summary,
        status=str(_enum_value(request_row.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/reviews", response_model=ReviewCycleResponse, status_code=201)
async def create_review_cycle(
    tender_id: int,
    contribution_id: int,
    data: ReviewCycleCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    review = ReviewCycle(
        contribution_unit_id=contribution.id,
        reviewer_id=data.reviewer_id,
        stage_name=data.stage_name,
        started_at=data.started_at or _now_utc(),
        notes=data.notes,
        status=ReviewCycleStatus.OPEN,
    )
    contribution.status = ContributionUnitStatus.IN_REVIEW
    db.add(review)
    await db.flush()
    await db.refresh(review)
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "review_cycle_started",
                build_review_cycle_started_event_payload(review=review, contribution=contribution),
            )
        ],
    )

    return ReviewCycleResponse(
        id=review.id,
        contribution_unit_id=review.contribution_unit_id,
        reviewer_id=review.reviewer_id,
        stage_name=review.stage_name,
        started_at=review.started_at,
        completed_at=review.completed_at,
        outcome=review.outcome,
        notes=review.notes,
        status=str(_enum_value(review.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/reviews/{review_id}/complete", response_model=ReviewCycleResponse)
async def complete_review_cycle(
    tender_id: int,
    contribution_id: int,
    review_id: int,
    data: ReviewCycleComplete,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewCycleResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    review = await _load_review_or_404(db, contribution_id=contribution.id, review_id=review_id)

    review.completed_at = data.completed_at or _now_utc()
    review.outcome = data.outcome or review.outcome or "completed"
    if data.notes is not None:
        review.notes = data.notes
    review.status = ReviewCycleStatus.COMPLETED
    if str(review.outcome).strip().casefold() == "approved":
        contribution.status = ContributionUnitStatus.COMPLETED
    await db.flush()
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "contribution_review_completed",
                build_contribution_review_completed_event_payload(review=review, contribution=contribution),
            )
        ],
    )

    return ReviewCycleResponse(
        id=review.id,
        contribution_unit_id=review.contribution_unit_id,
        reviewer_id=review.reviewer_id,
        stage_name=review.stage_name,
        started_at=review.started_at,
        completed_at=review.completed_at,
        outcome=review.outcome,
        notes=review.notes,
        status=str(_enum_value(review.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/rework", response_model=ReworkResponse, status_code=201)
async def create_rework_action(
    tender_id: int,
    contribution_id: int,
    data: ReworkCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReworkResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    rework = ReworkAction(
        contribution_unit_id=contribution.id,
        review_cycle_id=data.review_cycle_id,
        requested_by=current_user.id,
        assigned_to_user_id=data.assigned_to_user_id,
        severity=data.severity,
        is_blocking=data.is_blocking,
        reason=data.reason,
        due_at=data.due_at,
        requested_at=data.requested_at or _now_utc(),
        status=ReworkStatus.OPEN,
    )
    contribution.status = ContributionUnitStatus.REWORK if data.is_blocking else ContributionUnitStatus.IN_REVIEW
    db.add(rework)
    await db.flush()
    await db.refresh(rework)
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "rework_requested",
                build_rework_requested_event_payload(rework=rework, contribution=contribution),
            )
        ],
    )

    return ReworkResponse(
        id=rework.id,
        contribution_unit_id=rework.contribution_unit_id,
        review_cycle_id=rework.review_cycle_id,
        assigned_to_user_id=rework.assigned_to_user_id,
        severity=rework.severity,
        is_blocking=rework.is_blocking,
        reason=rework.reason,
        due_at=rework.due_at,
        requested_at=rework.requested_at,
        resolved_at=rework.resolved_at,
        resolution_notes=rework.resolution_notes,
        status=str(_enum_value(rework.status)),
    )


@router.post("/{tender_id}/observability/contributions/{contribution_id}/rework/{rework_id}/resolve", response_model=ReworkResponse)
async def resolve_rework_action(
    tender_id: int,
    contribution_id: int,
    rework_id: int,
    data: ReworkResolve,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReworkResponse:
    await check_tender_access(tender_id, current_user, db)
    contribution = await _load_contribution_or_404(db, tender_id=tender_id, contribution_id=contribution_id)
    rework = await _load_rework_or_404(db, contribution_id=contribution.id, rework_id=rework_id)

    rework.resolved_at = data.resolved_at or _now_utc()
    rework.resolution_notes = data.resolution_notes
    rework.status = ReworkStatus.RESOLVED
    contribution.status = ContributionUnitStatus.RECEIVED
    await db.flush()
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "rework_resolved",
                build_rework_resolved_event_payload(rework=rework, contribution=contribution),
            )
        ],
    )

    return ReworkResponse(
        id=rework.id,
        contribution_unit_id=rework.contribution_unit_id,
        review_cycle_id=rework.review_cycle_id,
        assigned_to_user_id=rework.assigned_to_user_id,
        severity=rework.severity,
        is_blocking=rework.is_blocking,
        reason=rework.reason,
        due_at=rework.due_at,
        requested_at=rework.requested_at,
        resolved_at=rework.resolved_at,
        resolution_notes=rework.resolution_notes,
        status=str(_enum_value(rework.status)),
    )


@router.post("/{tender_id}/observability/gates", response_model=ComplianceGateResponse, status_code=201)
async def create_compliance_gate(
    tender_id: int,
    data: ComplianceGateCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceGateResponse:
    await check_tender_access(tender_id, current_user, db)
    gate = ComplianceGate(
        tender_id=tender_id,
        contribution_unit_id=data.contribution_unit_id,
        owner_user_id=data.owner_user_id,
        gate_name=data.gate_name,
        due_at=data.due_at,
        decision_notes=data.decision_notes,
        status=ComplianceGateStatus.OPEN,
    )
    db.add(gate)
    await db.flush()
    await db.refresh(gate)
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "compliance_gate_opened",
                build_compliance_gate_opened_event_payload(gate=gate),
            )
        ],
    )

    return ComplianceGateResponse(
        id=gate.id,
        tender_id=gate.tender_id,
        contribution_unit_id=gate.contribution_unit_id,
        owner_user_id=gate.owner_user_id,
        gate_name=gate.gate_name,
        due_at=gate.due_at,
        evaluated_at=gate.evaluated_at,
        decision_notes=gate.decision_notes,
        status=str(_enum_value(gate.status)),
    )


@router.post("/{tender_id}/observability/gates/{gate_id}/decision", response_model=ComplianceGateResponse)
async def decide_compliance_gate(
    tender_id: int,
    gate_id: int,
    data: ComplianceGateDecision,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ComplianceGateResponse:
    await check_tender_access(tender_id, current_user, db)
    gate = await _load_gate_or_404(db, tender_id=tender_id, gate_id=gate_id)

    gate.status = data.status
    gate.evaluated_at = data.evaluated_at or _now_utc()
    if data.decision_notes is not None:
        gate.decision_notes = data.decision_notes
    await db.flush()

    event_type = "compliance_gate_passed" if gate.status == ComplianceGateStatus.PASSED else "compliance_gate_failed"
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                event_type,
                build_compliance_gate_decision_event_payload(gate=gate),
            )
        ],
    )

    return ComplianceGateResponse(
        id=gate.id,
        tender_id=gate.tender_id,
        contribution_unit_id=gate.contribution_unit_id,
        owner_user_id=gate.owner_user_id,
        gate_name=gate.gate_name,
        due_at=gate.due_at,
        evaluated_at=gate.evaluated_at,
        decision_notes=gate.decision_notes,
        status=str(_enum_value(gate.status)),
    )


@router.post("/{tender_id}/observability/calls", response_model=CallSessionResponse, status_code=201)
async def create_call_session(
    tender_id: int,
    data: CallSessionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CallSessionResponse:
    await check_tender_access(tender_id, current_user, db)
    call = CallSession(
        tender_id=tender_id,
        title=data.title,
        scheduled_at=data.scheduled_at,
        status=CallSessionStatus.SCHEDULED,
        created_by=current_user.id,
    )
    db.add(call)
    await db.flush()
    await db.refresh(call)
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "call_scheduled",
                build_call_scheduled_event_payload(call=call),
            )
        ],
    )

    return CallSessionResponse(
        id=call.id,
        tender_id=call.tender_id,
        title=call.title,
        scheduled_at=call.scheduled_at,
        started_at=call.started_at,
        ended_at=call.ended_at,
        status=str(_enum_value(call.status)),
    )


@router.post("/{tender_id}/observability/calls/{call_id}/attendance", response_model=AttendanceRecordResponse, status_code=201)
async def upsert_attendance_record(
    tender_id: int,
    call_id: int,
    data: AttendanceRecordUpsert,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AttendanceRecordResponse:
    await check_tender_access(tender_id, current_user, db)
    call = await _load_call_or_404(db, tender_id=tender_id, call_id=call_id)

    existing_query = select(AttendanceRecord).where(AttendanceRecord.call_session_id == call.id)
    if data.user_id is not None:
        existing_query = existing_query.where(AttendanceRecord.user_id == data.user_id)
    elif data.attendee_label:
        existing_query = existing_query.where(AttendanceRecord.attendee_label == data.attendee_label)
    else:
        raise HTTPException(status_code=400, detail="Either user_id or attendee_label is required")

    result = await db.execute(existing_query)
    record = result.scalar_one_or_none()
    if record is None:
        record = AttendanceRecord(
            call_session_id=call.id,
            user_id=data.user_id,
            attendee_label=data.attendee_label,
            attendance_status=data.attendance_status,
            recorded_at=data.recorded_at or _now_utc(),
            notes=data.notes,
        )
        db.add(record)
    else:
        record.attendance_status = data.attendance_status
        record.recorded_at = data.recorded_at or _now_utc()
        record.notes = data.notes
    await db.flush()
    await db.refresh(record)
    if data.attendance_status == AttendanceStatus.ATTENDED:
        call.status = CallSessionStatus.COMPLETED
    await _publish_operational_events(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        events=[
            (
                "call_attendance_recorded",
                build_call_attendance_recorded_event_payload(record=record, call=call),
            )
        ],
    )

    return AttendanceRecordResponse(
        id=record.id,
        call_session_id=record.call_session_id,
        user_id=record.user_id,
        attendee_label=record.attendee_label,
        attendance_status=str(_enum_value(record.attendance_status)),
        recorded_at=record.recorded_at,
        notes=record.notes,
    )
