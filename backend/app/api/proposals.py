"""
TenderWriter — Proposals API

CRUD endpoints for managing proposals and their sections.
All endpoints are protected with JWT auth. Access is checked via the associated tender's RBAC.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models import Proposal, ProposalSection, ProposalStatus, SectionStatus, Tender, TenderPermission, TenderStatus
from app.api.auth import get_current_user, UserResponse
from app.services.chat import ensure_official_chat_room, sync_chat_members_from_tender_permissions
from app.services.kpi_reason_engine import (
    build_draft_integrated_ready_event_payload,
    build_proposal_created_event_payload,
    build_proposal_section_updated_event_payload,
    build_submission_status_event_payload,
    build_tender_submitted_event_payload,
    publish_domain_event,
    publish_tender_sync,
    sync_tender_and_publish_event,
)
from app.services.compliance_observability import sync_requirement_compliance_and_gate
from app.services.operational_workflow import ensure_contribution_for_section, sync_section_operational_workflow

router = APIRouter()


# ── Helpers ──


def _normalize_section_content(content: dict | str | None) -> dict:
    """Normalize section content to TipTap JSON format.

    The DB column is JSONB and downstream code (OnlyOffice integration,
    _section_content_to_text) expects a TipTap dict with {"type": "doc", ...}.
    If a raw string is passed, wrap it in TipTap paragraph format.
    """
    if content is None:
        return {}
    if isinstance(content, dict):
        return content
    if isinstance(content, str) and content.strip():
        return {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": para}],
                }
                for para in content.split("\n\n")
                if para.strip()
            ] or [{"type": "paragraph", "content": [{"type": "text", "text": ""}]}],
        }
    return {}


# ── Schemas ──


class SectionCreate(BaseModel):
    title: str
    content: dict | str = {}
    order: int = 0


class SectionUpdate(BaseModel):
    title: str | None = None
    content: dict | str | None = None
    order: int | None = None
    status: SectionStatus | None = None
    assigned_to: int | None = None


class SectionResponse(BaseModel):
    id: int
    title: str
    content: dict | str
    order: int
    status: str
    assigned_to: int | None
    created_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ProposalCreate(BaseModel):
    tender_id: int
    title: str
    notes: str | None = None


class ProposalUpdate(BaseModel):
    title: str | None = None
    status: ProposalStatus | None = None
    notes: str | None = None


class ProposalResponse(BaseModel):
    id: int
    tender_id: int
    title: str
    status: str
    version: int
    notes: str | None
    created_at: datetime | None
    section_count: int = 0

    model_config = {"from_attributes": True}


class ProposalDetailResponse(ProposalResponse):
    sections: list[SectionResponse] = []


class ProposalListResponse(BaseModel):
    items: list[ProposalResponse]
    total: int


# ── Helpers ──


async def _check_tender_access_for_proposal(
    tender_id: int, user: UserResponse, db: AsyncSession
):
    """Verify the current user has access to the tender that owns a proposal."""
    if user.role == "admin":
        return

    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    if tender.created_by == user.id:
        return

    perm = await db.execute(
        select(TenderPermission).where(
            TenderPermission.tender_id == tender_id,
            TenderPermission.user_id == user.id,
        )
    )
    if perm.scalar_one_or_none():
        return

    raise HTTPException(status_code=404, detail="Proposal not found")


# ── Proposal Routes ──


@router.get("", response_model=ProposalListResponse)
async def list_proposals(
    tender_id: int | None = None,
    status: ProposalStatus | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List proposals with optional filtering by tender or status. RBAC-filtered."""
    query = select(Proposal)

    # RBAC: non-admin can only see proposals for tenders they own or have permission to
    if current_user.role != "admin":
        permitted_tender_ids = (
            select(TenderPermission.tender_id)
            .where(TenderPermission.user_id == current_user.id)
        )
        owned_tender_ids = (
            select(Tender.id).where(Tender.created_by == current_user.id)
        )
        query = query.where(
            or_(
                Proposal.tender_id.in_(owned_tender_ids),
                Proposal.tender_id.in_(permitted_tender_ids),
            )
        )

    if tender_id:
        query = query.where(Proposal.tender_id == tender_id)
    if status:
        query = query.where(Proposal.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Proposal.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    proposals = result.scalars().all()

    return ProposalListResponse(
        items=[
            ProposalResponse(
                id=p.id,
                tender_id=p.tender_id,
                title=p.title,
                status=p.status.value if p.status else "draft",
                version=p.version or 1,
                notes=p.notes,
                created_at=p.created_at,
            )
            for p in proposals
        ],
        total=total,
    )


@router.post("", response_model=ProposalResponse, status_code=201)
async def create_proposal(
    data: ProposalCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new proposal for a tender. RBAC-checked via tender."""
    await _check_tender_access_for_proposal(data.tender_id, current_user, db)

    proposal = Proposal(
        tender_id=data.tender_id,
        title=data.title,
        notes=data.notes,
        status=ProposalStatus.DRAFT,
        version=1,
        created_by=current_user.id,
    )
    db.add(proposal)

    # Automatically set tender to IN_PROGRESS
    result = await db.execute(select(Tender).where(Tender.id == data.tender_id))
    tender = result.scalar_one_or_none()
    if tender and tender.status in [TenderStatus.DRAFT, TenderStatus.ACTIVE]:
        tender.status = TenderStatus.IN_PROGRESS

    await db.flush()
    await db.refresh(proposal)

    await ensure_official_chat_room(
        db,
        tender_id=data.tender_id,
        actor_id=current_user.id,
        open_now=True,
    )
    await sync_chat_members_from_tender_permissions(
        db,
        tender_id=data.tender_id,
        actor_id=current_user.id,
    )

    await sync_tender_and_publish_event(
        db,
        tender_id=data.tender_id,
        actor_id=current_user.id,
        event_type="proposal_created",
        event_payload=build_proposal_created_event_payload(
            proposal=proposal,
            section_count=0,
        ),
    )

    return ProposalResponse(
        id=proposal.id,
        tender_id=proposal.tender_id,
        title=proposal.title,
        status=proposal.status.value,
        version=proposal.version,
        notes=proposal.notes,
        created_at=proposal.created_at,
        section_count=0,
    )


@router.get("/{proposal_id}", response_model=ProposalDetailResponse)
async def get_proposal(
    proposal_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a proposal with all its sections. RBAC-checked via tender."""
    result = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id)
        .options(selectinload(Proposal.sections))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    return ProposalDetailResponse(
        id=proposal.id,
        tender_id=proposal.tender_id,
        title=proposal.title,
        status=proposal.status.value if proposal.status else "draft",
        version=proposal.version or 1,
        notes=proposal.notes,
        created_at=proposal.created_at,
        section_count=len(proposal.sections),
        sections=[
            SectionResponse(
                id=s.id,
                title=s.title,
                content=s.content or {},
                order=s.order or 0,
                status=s.status.value if s.status else "todo",
                assigned_to=s.assigned_to,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sorted(proposal.sections, key=lambda x: x.order or 0)
        ],
    )


@router.put("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: int,
    data: ProposalUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update proposal metadata. RBAC-checked via tender."""
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    previous_status = proposal.status if proposal else None
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(proposal, key, value)

    # Automatically set tender to SUBMITTED if proposal is submitted
    if data.status == ProposalStatus.SUBMITTED:
        result = await db.execute(select(Tender).where(Tender.id == proposal.tender_id))
        tender = result.scalar_one_or_none()
        if tender:
            tender.status = TenderStatus.SUBMITTED

    await db.flush()
    await db.refresh(proposal)

    compliance_events = await sync_requirement_compliance_and_gate(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
    )



    if proposal.status == ProposalStatus.SUBMITTED and proposal.status != previous_status:
        await sync_tender_and_publish_event(
            db,
            tender_id=proposal.tender_id,
            actor_id=current_user.id,
            event_type="tender_submitted",
            event_payload=build_tender_submitted_event_payload(
                submitted_at=datetime.now(timezone.utc),
                channel="proposal_status_update",
            ),
        )
    else:
        await publish_tender_sync(
            db,
            tender_id=proposal.tender_id,
            actor_id=current_user.id,
        )

    for event_type, payload in compliance_events:
        await publish_domain_event(
            db,
            tender_id=proposal.tender_id,
            actor_id=current_user.id,
            event_type=event_type,
            payload=payload,
        )

    return ProposalResponse(
        id=proposal.id,
        tender_id=proposal.tender_id,
        title=proposal.title,
        status=proposal.status.value if proposal.status else "draft",
        version=proposal.version or 1,
        notes=proposal.notes,
        created_at=proposal.created_at,
    )


# ── Section Routes ──


@router.get("/{proposal_id}/sections", response_model=list[SectionResponse])
async def list_sections(
    proposal_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sections for a proposal. RBAC-checked via tender."""
    prop_result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = prop_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    result = await db.execute(
        select(ProposalSection)
        .where(ProposalSection.proposal_id == proposal_id)
        .order_by(ProposalSection.order)
    )
    sections = result.scalars().all()

    return [
        SectionResponse(
            id=s.id,
            title=s.title,
            content=s.content or {},
            order=s.order or 0,
            status=s.status.value if s.status else "todo",
            assigned_to=s.assigned_to,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sections
    ]


@router.get("/{proposal_id}/sections/{section_id}", response_model=SectionResponse)
async def get_section(
    proposal_id: int,
    section_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single proposal section. RBAC-checked via tender."""
    # First get the proposal to check tender access
    prop_result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = prop_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    result = await db.execute(
        select(ProposalSection).where(
            ProposalSection.id == section_id,
            ProposalSection.proposal_id == proposal_id,
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    return SectionResponse(
        id=section.id,
        title=section.title,
        content=section.content or {},
        order=section.order or 0,
        status=section.status.value if section.status else "todo",
        assigned_to=section.assigned_to,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


@router.put("/{proposal_id}/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    proposal_id: int,
    section_id: int,
    data: SectionUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a proposal section (content, status, assignment). RBAC-checked via tender."""
    prop_result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = prop_result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    result = await db.execute(
        select(ProposalSection).where(
            ProposalSection.id == section_id,
            ProposalSection.proposal_id == proposal_id,
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    previous_status = section.status or SectionStatus.TODO
    previous_assigned_to = section.assigned_to
    changed_fields = list(data.model_dump(exclude_unset=True).keys())
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "content":
            value = _normalize_section_content(value)
        setattr(section, key, value)

    await db.flush()
    await db.refresh(section)

    operational_events = await sync_section_operational_workflow(
        db,
        tender_id=proposal.tender_id,
        section=section,
        actor_id=current_user.id,
        previous_status=previous_status,
        previous_assigned_to=previous_assigned_to,
    )

    compliance_events = await sync_requirement_compliance_and_gate(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
    )



    await sync_tender_and_publish_event(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
        event_type="proposal_section_updated",
        event_payload=build_proposal_section_updated_event_payload(
            section=section,
            change_type="section_updated",
            changed_fields=changed_fields,
        ),
    )

    for event_type, payload in operational_events:
        await publish_domain_event(
            db,
            tender_id=proposal.tender_id,
            actor_id=current_user.id,
            event_type=event_type,
            payload=payload,
        )

    for event_type, payload in compliance_events:
        await publish_domain_event(
            db,
            tender_id=proposal.tender_id,
            actor_id=current_user.id,
            event_type=event_type,
            payload=payload,
        )

    return SectionResponse(
        id=section.id,
        title=section.title,
        content=section.content or {},
        order=section.order or 0,
        status=section.status.value if section.status else "todo",
        assigned_to=section.assigned_to,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


@router.post("/{proposal_id}/sections", response_model=SectionResponse, status_code=201)
async def add_section(
    proposal_id: int,
    data: SectionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new section to a proposal. RBAC-checked via tender."""
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    section = ProposalSection(
        proposal_id=proposal_id,
        title=data.title,
        content=_normalize_section_content(data.content),
        order=data.order,
        status=SectionStatus.TODO,
    )
    db.add(section)
    await db.flush()
    await db.refresh(section)

    await ensure_contribution_for_section(
        db,
        tender_id=proposal.tender_id,
        section=section,
        actor_id=current_user.id,
    )

    await sync_tender_and_publish_event(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
        event_type="proposal_section_updated",
        event_payload=build_proposal_section_updated_event_payload(
            section=section,
            change_type="section_created",
            changed_fields=["title", "content", "order", "status"],
        ),
    )

    return SectionResponse(
        id=section.id,
        title=section.title,
        content=section.content or {},
        order=section.order or 0,
        status=section.status.value,
        assigned_to=section.assigned_to,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )


class BulkSectionCreate(BaseModel):
    sections: list[str]


@router.post(
    "/{proposal_id}/sections/bulk",
    response_model=list[SectionResponse],
    status_code=201,
)
async def bulk_create_sections(
    proposal_id: int,
    data: BulkSectionCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple sections at once for a proposal."""
    result = await db.execute(select(Proposal).where(Proposal.id == proposal_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)

    created_sections: list[ProposalSection] = []
    for idx, title in enumerate(data.sections):
        section = ProposalSection(
            proposal_id=proposal_id,
            title=title,
            content={},
            order=idx,
            status=SectionStatus.TODO,
        )
        db.add(section)
        created_sections.append(section)

    await db.flush()

    for section in created_sections:
        await ensure_contribution_for_section(
            db,
            tender_id=proposal.tender_id,
            section=section,
            actor_id=current_user.id,
        )

    await sync_tender_and_publish_event(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
        event_type="proposal_section_updated",
        event_payload={
            "proposal_id": proposal_id,
            "change_type": "bulk_sections_created",
            "section_count": len(created_sections),
        },
    )

    return [
        SectionResponse(
            id=s.id,
            title=s.title,
            content=s.content or {},
            order=s.order or 0,
            status=s.status.value,
            assigned_to=s.assigned_to,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in created_sections
    ]


class ProposalDraftReadyRequest(BaseModel):
    ready_at: datetime | None = None


class ProposalSubmissionStatusRequest(BaseModel):
    submission_status: str
    occurred_at: datetime | None = None
    channel: str = "manual_admin_update"
    reference_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class ProposalLifecycleActionResponse(BaseModel):
    status: str
    event_type: str
    proposal_id: int
    tender_id: int
    payload: dict


_ALLOWED_SUBMISSION_STATUSES = {"acknowledged", "failed"}


def _utc_or_now(value: datetime | None) -> datetime:
    return value or datetime.now(timezone.utc)


def _clone_tender_metadata(tender: Tender) -> dict:
    return dict(tender.metadata_json or {})


@router.post("/{proposal_id}/draft-ready", response_model=ProposalLifecycleActionResponse, status_code=202)
async def mark_proposal_draft_ready(
    proposal_id: int,
    data: ProposalDraftReadyRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id)
        .options(selectinload(Proposal.sections), selectinload(Proposal.tender))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)
    occurred_at = _utc_or_now(data.ready_at)
    tender = proposal.tender
    if tender is None:
        raise HTTPException(status_code=404, detail="Tender not found")

    approved_section_count = sum(1 for section in proposal.sections if section.status == SectionStatus.APPROVED)
    total_section_count = len(proposal.sections)
    metadata = _clone_tender_metadata(tender)
    lifecycle = dict(metadata.get("lifecycle") or {})
    lifecycle["draft_ready"] = {
        "proposal_id": proposal.id,
        "ready_at": occurred_at.isoformat(),
        "approved_section_count": approved_section_count,
        "total_section_count": total_section_count,
        "actor_id": current_user.id,
    }
    metadata["lifecycle"] = lifecycle
    tender.metadata_json = metadata
    await db.flush()

    payload = build_draft_integrated_ready_event_payload(
        ready_at=occurred_at,
        proposal_id=proposal.id,
        approved_section_count=approved_section_count,
        total_section_count=total_section_count,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
        event_type="draft_integrated_ready",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return ProposalLifecycleActionResponse(status="accepted", event_type="draft_integrated_ready", proposal_id=proposal.id, tender_id=proposal.tender_id, payload=payload)


@router.post("/{proposal_id}/submission-status", response_model=ProposalLifecycleActionResponse, status_code=202)
async def record_proposal_submission_status(
    proposal_id: int,
    data: ProposalSubmissionStatusRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Proposal)
        .where(Proposal.id == proposal_id)
        .options(selectinload(Proposal.tender))
    )
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    await _check_tender_access_for_proposal(proposal.tender_id, current_user, db)
    submission_status = data.submission_status.strip().casefold()
    if submission_status not in _ALLOWED_SUBMISSION_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported submission status")

    occurred_at = _utc_or_now(data.occurred_at)
    tender = proposal.tender
    if tender is None:
        raise HTTPException(status_code=404, detail="Tender not found")

    metadata = _clone_tender_metadata(tender)
    lifecycle = dict(metadata.get("lifecycle") or {})
    lifecycle["submission_status"] = {
        "proposal_id": proposal.id,
        "submission_status": submission_status,
        "occurred_at": occurred_at.isoformat(),
        "channel": data.channel,
        "reference_id": data.reference_id,
        "error_code": data.error_code,
        "error_message": data.error_message,
        "actor_id": current_user.id,
    }
    metadata["lifecycle"] = lifecycle
    tender.metadata_json = metadata
    await db.flush()

    event_type = "submission_acknowledged" if submission_status == "acknowledged" else "submission_failed"
    payload = build_submission_status_event_payload(
        submission_status=submission_status,
        occurred_at=occurred_at,
        channel=data.channel,
        reference_id=data.reference_id,
        error_code=data.error_code,
        error_message=data.error_message,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=proposal.tender_id,
        actor_id=current_user.id,
        event_type=event_type,
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return ProposalLifecycleActionResponse(status="accepted", event_type=event_type, proposal_id=proposal.id, tender_id=proposal.tender_id, payload=payload)

