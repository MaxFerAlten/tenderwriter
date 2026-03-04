"""
TenderWriter — Proposals API

CRUD endpoints for managing proposals and their sections.
All endpoints are protected with JWT auth. Access is checked via the associated tender's RBAC.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models import Proposal, ProposalSection, ProposalStatus, SectionStatus, Tender, TenderPermission, TenderStatus
from app.api.auth import get_current_user, UserResponse

router = APIRouter()


# ── Schemas ──


class SectionCreate(BaseModel):
    title: str
    content: dict = {}
    order: int = 0


class SectionUpdate(BaseModel):
    title: str | None = None
    content: dict | None = None
    order: int | None = None
    status: SectionStatus | None = None
    assigned_to: int | None = None


class SectionResponse(BaseModel):
    id: int
    title: str
    content: dict
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

    # Create default sections
    default_sections = [
        "Executive Summary",
        "Company Overview",
        "Technical Approach",
        "Team & Key Personnel",
        "Past Performance & References",
        "Project Timeline",
        "Pricing & Budget",
        "Compliance Matrix",
    ]

    for idx, title in enumerate(default_sections):
        section = ProposalSection(
            proposal_id=proposal.id,
            title=title,
            content={},
            order=idx,
            status=SectionStatus.TODO,
        )
        db.add(section)

    await db.flush()

    return ProposalResponse(
        id=proposal.id,
        tender_id=proposal.tender_id,
        title=proposal.title,
        status=proposal.status.value,
        version=proposal.version,
        notes=proposal.notes,
        created_at=proposal.created_at,
        section_count=len(default_sections),
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

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(section, key, value)

    await db.flush()
    await db.refresh(section)

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
        content=data.content,
        order=data.order,
        status=SectionStatus.TODO,
    )
    db.add(section)
    await db.flush()
    await db.refresh(section)

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
