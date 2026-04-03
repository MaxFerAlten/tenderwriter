"""
TenderWriter — Tenders API

CRUD endpoints for managing tenders (RFPs/ITTs).
Includes document upload + ingestion trigger and requirement management.
All endpoints are protected with JWT auth and granular RBAC.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models import Tender, TenderRequirement, TenderStatus, ComplianceStatus, TenderPermission
from app.api.auth import get_current_user, UserResponse
from app.utils.naming import get_tender_upload_path
from app.services.chat import ensure_official_chat_room, sync_chat_members_from_tender_permissions
from app.services.kpi_reason_engine import (
    build_bid_plan_event_payload,
    build_bid_team_assigned_event_payload,
    build_clarification_event_payload,
    build_compliance_gate_rework_requested_event_payload,
    build_contribution_wave_event_payload,
    build_coordination_risk_raised_event_payload,
    build_rework_reescalated_to_coordination_event_payload,
    build_requirements_extracted_event_payload,
    build_tender_created_event_payload,
    build_tender_decision_event_payload,
    build_tender_document_ingested_event_payload,
    build_tender_outcome_recorded_event_payload,
    build_terminal_lifecycle_event_payload,
    build_tender_stopped_at_gate_event_payload,
    publish_domain_event,
    publish_tender_sync,
    sync_tender_and_publish_event,
)
from app.services.compliance_observability import sync_requirement_compliance_and_gate
from app.services.tender_requirements import (
    apply_extracted_requirement_candidates,
    sync_tender_requirements_to_graph,
)

router = APIRouter()


# ── Schemas ──


class TenderCreate(BaseModel):
    title: str
    client: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    category: str | None = None
    tags: list[str] = []
    budget_estimate: float | None = None


class TenderUpdate(BaseModel):
    title: str | None = None
    client: str | None = None
    description: str | None = None
    deadline: datetime | None = None
    status: TenderStatus | None = None
    category: str | None = None
    tags: list[str] | None = None
    budget_estimate: float | None = None


class RequirementResponse(BaseModel):
    id: int
    requirement_text: str
    category: str | None
    priority: str
    compliance_status: str
    mapped_section_id: int | None = None
    mapped_section_title: str | None = None

    model_config = {"from_attributes": True}


class TenderResponse(BaseModel):
    id: int
    title: str
    client: str | None
    description: str | None
    deadline: datetime | None
    status: str
    category: str | None
    tags: list[str]
    budget_estimate: float | None
    created_at: datetime | None
    requirement_count: int = 0
    proposal_id: int | None = None
    created_by: int | None = None
    created_by_name: str | None = None
    lifecycle_metadata: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class TenderDetailResponse(TenderResponse):
    requirements: list[RequirementResponse] = []


class TenderListResponse(BaseModel):
    items: list[TenderResponse]
    total: int


# ── Helpers ──


_TITLE_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_tender_title(title: str) -> str:
    return _TITLE_WHITESPACE_RE.sub(" ", (title or "").strip())


def _tender_title_lookup_key(title: str) -> str:
    return _normalize_tender_title(title).lower()


async def _ensure_unique_tender_title(
    db: AsyncSession,
    title: str,
    *,
    exclude_tender_id: int | None = None,
) -> str:
    normalized_title = _normalize_tender_title(title)
    if not normalized_title:
        raise HTTPException(status_code=400, detail="Tender title is required")

    lookup_key = normalized_title.lower()

    # Serialize competing writes for the same logical title without requiring
    # a schema migration that could fail on databases already containing duplicates.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lookup_key))"),
        {"lookup_key": lookup_key},
    )

    normalized_db_title = func.lower(
        func.regexp_replace(
            func.btrim(Tender.title),
            r"\s+",
            " ",
            "g",
        )
    )
    query = select(Tender.id).where(normalized_db_title == lookup_key)
    if exclude_tender_id is not None:
        query = query.where(Tender.id != exclude_tender_id)

    existing_tender_id = (await db.execute(query.limit(1))).scalar_one_or_none()
    if existing_tender_id is not None:
        raise HTTPException(status_code=409, detail="A tender with this title already exists.")

    return normalized_title


async def check_tender_access(
    tender_id: int, user: UserResponse, db: AsyncSession
) -> Tender:
    """
    Check that the current user has access to the given tender.
    Returns the tender if access is granted, raises 404 otherwise.
    """
    result = await db.execute(
        select(Tender)
        .where(Tender.id == tender_id)
        .options(
            selectinload(Tender.requirements).selectinload(TenderRequirement.proposal_section),
            selectinload(Tender.created_by_user),
            selectinload(Tender.proposals),
        )
    )
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    # Admin has full access
    if user.role == "admin":
        return tender

    # Owner has full access
    if tender.created_by == user.id:
        return tender

    # Check explicit permission
    perm_result = await db.execute(
        select(TenderPermission).where(
            TenderPermission.tender_id == tender_id,
            TenderPermission.user_id == user.id,
        )
    )
    if perm_result.scalar_one_or_none():
        return tender

    raise HTTPException(status_code=404, detail="Tender not found")


def _tender_to_response(tender: Tender) -> TenderResponse:
    """Convert a Tender model to TenderResponse."""
    creator_name = None
    # Use inspect to check if created_by_user was loaded to avoid lazy-load errors
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(tender)
    if 'created_by_user' not in insp.unloaded and tender.created_by_user:
        creator_name = tender.created_by_user.name

    req_count = 0
    if 'requirements' not in insp.unloaded and tender.requirements:
        req_count = len(tender.requirements)

    prop_id = None
    if 'proposals' not in insp.unloaded and tender.proposals and len(tender.proposals) > 0:
        prop_id = tender.proposals[0].id

    return TenderResponse(
        id=tender.id,
        title=tender.title,
        client=tender.client,
        description=tender.description,
        deadline=tender.deadline,
        status=tender.status.value if tender.status else "draft",
        category=tender.category,
        tags=tender.tags or [],
        budget_estimate=tender.budget_estimate,
        created_at=tender.created_at,
        requirement_count=req_count,
        proposal_id=prop_id,
        created_by=tender.created_by,
        created_by_name=creator_name,
        lifecycle_metadata=dict((tender.metadata_json or {}).get("lifecycle") or {}),
    )


def _requirement_to_response(requirement: TenderRequirement) -> RequirementResponse:
    mapped_section = requirement.proposal_section
    return RequirementResponse(
        id=requirement.id,
        requirement_text=requirement.requirement_text,
        category=requirement.category,
        priority=requirement.priority,
        compliance_status=requirement.compliance_status.value,
        mapped_section_id=requirement.proposal_section_id,
        mapped_section_title=mapped_section.title if mapped_section else None,
    )


# ── Routes ──


@router.get("", response_model=TenderListResponse)
async def list_tenders(
    status: TenderStatus | None = None,
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tenders with filtering, search, and pagination. RBAC-filtered."""
    query = select(Tender).options(
        selectinload(Tender.created_by_user),
        selectinload(Tender.proposals),
    )

    # RBAC filter: non-admin sees only own tenders + tenders with explicit permission
    if current_user.role != "admin":
        permitted_subq = (
            select(TenderPermission.tender_id)
            .where(TenderPermission.user_id == current_user.id)
        )
        query = query.where(
            or_(
                Tender.created_by == current_user.id,
                Tender.id.in_(permitted_subq),
            )
        )

    if status:
        query = query.where(Tender.status == status)
    if category:
        query = query.where(Tender.category == category)
    if search:
        escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Tender.title.ilike(f"%{escaped_search}%", escape="\\"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch page
    query = query.order_by(Tender.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    tenders = result.scalars().all()

    items = [_tender_to_response(t) for t in tenders]

    return TenderListResponse(items=items, total=total)


@router.post("", response_model=TenderResponse, status_code=201)
async def create_tender(
    data: TenderCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new tender. The creator is automatically set to the current user."""
    normalized_title = await _ensure_unique_tender_title(db, data.title)
    tender = Tender(
        title=normalized_title,
        client=data.client,
        description=data.description,
        deadline=data.deadline,
        category=data.category,
        tags=data.tags,
        budget_estimate=data.budget_estimate,
        status=TenderStatus.DRAFT,
        created_by=current_user.id,
    )
    db.add(tender)
    await db.flush()
    await db.refresh(tender)

    await ensure_official_chat_room(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        open_now=False,
    )
    await sync_chat_members_from_tender_permissions(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
    )

    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="tender_created",
        event_payload=build_tender_created_event_payload(tender),
    )

    return _tender_to_response(tender)


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a tender by ID with its requirements. RBAC-checked."""
    tender = await check_tender_access(tender_id, current_user, db)

    response = _tender_to_response(tender)
    return TenderDetailResponse(
        **response.model_dump(),
        requirements=[_requirement_to_response(r) for r in tender.requirements],
    )


@router.put("/{tender_id}", response_model=TenderResponse)
async def update_tender(
    tender_id: int,
    data: TenderUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a tender. RBAC-checked."""
    # First check access (uses eager loading for requirements/proposals)
    await check_tender_access(tender_id, current_user, db)

    # Re-fetch with FOR UPDATE lock to prevent concurrent overwrites
    result = await db.execute(
        select(Tender).where(Tender.id == tender_id).with_for_update()
    )
    tender = result.scalar_one()
    previous_status = tender.status

    update_data = data.model_dump(exclude_unset=True)
    if "title" in update_data:
        normalized_title = _normalize_tender_title(update_data["title"] or "")
        if _tender_title_lookup_key(normalized_title) == _tender_title_lookup_key(tender.title):
            update_data["title"] = normalized_title
        else:
            update_data["title"] = await _ensure_unique_tender_title(
                db,
                update_data["title"],
                exclude_tender_id=tender_id,
            )

    for key, value in update_data.items():
        setattr(tender, key, value)

    await db.flush()
    await db.refresh(tender)

    compliance_events = await sync_requirement_compliance_and_gate(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
    )
    await ensure_official_chat_room(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        open_now=False,
    )
    await sync_chat_members_from_tender_permissions(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
    )

    if tender.status in [TenderStatus.WON, TenderStatus.LOST, TenderStatus.CANCELLED] and tender.status != previous_status:
        await sync_tender_and_publish_event(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
            event_type="tender_outcome_recorded",
            event_payload=build_tender_outcome_recorded_event_payload(
                outcome=tender.status.value,
                recorded_at=datetime.now(timezone.utc),
            ),
        )
    else:
        await publish_tender_sync(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
        )

    for event_type, payload in compliance_events:
        await publish_domain_event(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
            event_type=event_type,
            payload=payload,
        )

    return _tender_to_response(tender)


@router.delete("/{tender_id}", status_code=204)
async def delete_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a tender and all associated data. RBAC-checked."""
    tender = await check_tender_access(tender_id, current_user, db)
    await db.delete(tender)
    await db.commit()
    # Note: orphaned MinIO files might still need cleanup explicitly later


@router.post("/{tender_id}/import", status_code=202)
async def import_tender_document(
    tender_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and process a tender document (PDF/DOCX). RBAC-checked.
    Triggers the ingestion pipeline: parse → extract requirements → index.
    """
    tender = await check_tender_access(tender_id, current_user, db)
    
    # Restrict uploads for finalized tenders
    if tender.status in [TenderStatus.SUBMITTED, TenderStatus.WON, TenderStatus.LOST, TenderStatus.CANCELLED]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot upload documents to a tender with status '{tender.status.value}'"
        )

    # 1. Upload to MinIO
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    bucket_name = settings.minio_bucket
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)

    # Determine user prefix for folder structure
    user_prefix = current_user.email.split('@')[0] if current_user.email else "unknown"

    # Determine structured path
    object_name = get_tender_upload_path(
        user_prefix=user_prefix,
        tender_title=tender.title,
        tender_id=tender.id,
        filename=file.filename
    )
    
    # Read file content to upload
    content = await file.read()
    import io
    file_stream = io.BytesIO(content)
    
    minio_client.put_object(
        bucket_name,
        object_name,
        file_stream,
        length=len(content),
        content_type=file.content_type,
    )

    # 2. Trigger Ingestion Pipeline
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    rag_engine = request.app.state.rag_engine
    await rag_engine.ensure_initialized()
    
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(rag_engine)
    
    try:
        stats = await pipeline.ingest_file(
            file_path=tmp_path,
            document_id=tender_id,
            doc_type="tender",
            metadata={"original_filename": file.filename}
        )
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    requirement_candidates = list(stats.get("requirement_candidates") or [])
    created_requirements = apply_extracted_requirement_candidates(tender, requirement_candidates)
    await db.flush()
    graph_synced = await sync_tender_requirements_to_graph(
        rag_engine,
        tender,
        list(tender.requirements or created_requirements),
    )
    stats["graph_synced"] = graph_synced
    compliance_events = await sync_requirement_compliance_and_gate(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
    )
    # 3. Update status to ACTIVE if it was DRAFT
    if tender.status == TenderStatus.DRAFT:
        tender.status = TenderStatus.ACTIVE
        await db.flush()
        await db.refresh(tender)

    # 4. Ensure official tender chat is open once the tender has started
    if tender.status in [TenderStatus.ACTIVE, TenderStatus.IN_PROGRESS]:
        await ensure_official_chat_room(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
            open_now=True,
        )
        await sync_chat_members_from_tender_permissions(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
        )

    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="tender_document_ingested",
        event_payload=build_tender_document_ingested_event_payload(
            document_id=object_name,
            filename=file.filename or "uploaded-document",
            stats=stats,
        ),
    )

    await publish_domain_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="requirements_extracted",
        payload=build_requirements_extracted_event_payload(
            document_id=object_name,
            filename=file.filename or "uploaded-document",
            extracted_candidates=requirement_candidates,
            created_requirements=created_requirements,
        ),
    )

    for event_type, payload in compliance_events:
        await publish_domain_event(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
            event_type=event_type,
            payload=payload,
        )

    return {
        "message": "Document uploaded and ingested successfully",
        "tender_id": tender_id,
        "filename": file.filename,
        "stats": stats,
    }



class TenderDecisionRequest(BaseModel):
    decision: str
    decided_at: datetime | None = None
    reason_code: str | None = None
    notes: str | None = None


class TenderBidPlanRequest(BaseModel):
    plan_status: str = "created"
    planned_at: datetime | None = None
    owner_user_ids: list[int] = []
    milestone_count: int | None = None
    notes: str | None = None


class ContributionWaveRequest(BaseModel):
    opened_at: datetime | None = None
    contribution_count: int | None = None
    department_count: int | None = None
    notes: str | None = None


class TenderOutcomeRecordRequest(BaseModel):
    outcome: str
    recorded_at: datetime | None = None
    reason_code: str | None = None
    notes: str | None = None


class TenderCoordinationRiskRequest(BaseModel):
    external_rework_id: str | None = None
    external_contribution_id: str | None = None
    severity: str | None = "high"
    reason_code: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None


class TenderCoordinationRecoveryRequest(BaseModel):
    external_rework_id: str | None = None
    external_contribution_id: str | None = None
    severity: str | None = "high"
    reason_code: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None


class TenderGateLifecycleRequest(BaseModel):
    external_gate_id: str | None = None
    gate_name: str | None = None
    external_rework_id: str | None = None
    reason_code: str | None = None
    notes: str | None = None
    occurred_at: datetime | None = None


class TenderClarificationCreate(BaseModel):
    request_id: str | None = None
    request_summary: str
    deadline_at: datetime | None = None
    source_label: str | None = None
    occurred_at: datetime | None = None


class TenderClarificationUpdate(BaseModel):
    response_summary: str | None = None
    occurred_at: datetime | None = None
    source_label: str | None = None


class TenderLifecycleActionResponse(BaseModel):
    status: str
    event_type: str
    tender_id: int
    payload: dict


_ALLOWED_DECISIONS = {"go", "no_bid"}
_ALLOWED_BID_PLAN_STATUSES = {"created", "approved"}
_ALLOWED_OUTCOMES = {"won", "lost", "excluded", "withdrawn", "stopped", "cancelled"}


def _utc_or_now(value: datetime | None) -> datetime:
    return value or datetime.now(timezone.utc)


def _clone_tender_metadata(tender: Tender) -> dict:
    return dict(tender.metadata_json or {})


def _clone_lifecycle_metadata(tender: Tender) -> tuple[dict, dict]:
    metadata = _clone_tender_metadata(tender)
    lifecycle = dict(metadata.get("lifecycle") or {})
    return metadata, lifecycle


def _store_lifecycle_metadata(tender: Tender, *, metadata: dict, lifecycle: dict) -> None:
    metadata["lifecycle"] = lifecycle
    tender.metadata_json = metadata


def _apply_structured_outcome(
    tender: Tender,
    *,
    metadata: dict,
    lifecycle: dict,
    outcome: str,
    recorded_at: datetime,
    reason_code: str | None,
    notes: str | None,
    actor_id: int,
) -> None:
    lifecycle["structured_outcome"] = {
        "outcome": outcome,
        "recorded_at": recorded_at.isoformat(),
        "reason_code": reason_code,
        "notes": notes,
        "actor_id": actor_id,
    }
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)

    if outcome == "won":
        tender.status = TenderStatus.WON
    elif outcome == "lost":
        tender.status = TenderStatus.LOST
    elif outcome in {"excluded", "withdrawn", "stopped", "cancelled"}:
        tender.status = TenderStatus.CANCELLED


def _event_type_for_structured_outcome(outcome: str) -> str:
    if outcome == "won":
        return "award_confirmed"
    if outcome == "lost":
        return "loss_reason_recorded"
    if outcome == "excluded":
        return "tender_excluded"
    if outcome == "withdrawn":
        return "tender_withdrawn"
    return "tender_stopped"


def _upsert_clarification_record(
    *,
    lifecycle: dict,
    request_id: str,
    payload: dict,
    allow_create: bool = True,
) -> dict | None:
    clarifications = list(lifecycle.get("clarifications") or [])
    updated: dict | None = None
    for item in clarifications:
        if str(item.get("request_id")) == request_id:
            item.update(payload)
            updated = item
            break
    if updated is None:
        if not allow_create:
            return None
        updated = {"request_id": request_id, **payload}
        clarifications.append(updated)
    lifecycle["clarifications"] = clarifications
    return updated


@router.post("/{tender_id}/decision", response_model=TenderLifecycleActionResponse, status_code=202)
async def record_tender_decision(
    tender_id: int,
    data: TenderDecisionRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    decision = data.decision.strip().casefold()
    if decision not in _ALLOWED_DECISIONS:
        raise HTTPException(status_code=400, detail="Unsupported tender decision")

    decided_at = _utc_or_now(data.decided_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    lifecycle["decision"] = {
        "decision": decision,
        "decided_at": decided_at.isoformat(),
        "reason_code": data.reason_code,
        "notes": data.notes,
        "actor_id": current_user.id,
    }
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    event_type = "go_decision_recorded" if decision == "go" else "no_bid_decision_recorded"
    payload = build_tender_decision_event_payload(
        decision=decision,
        decided_at=decided_at,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type=event_type,
        event_payload=payload,
        occurred_at=decided_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type=event_type, tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/bid-plan", response_model=TenderLifecycleActionResponse, status_code=202)
async def record_tender_bid_plan(
    tender_id: int,
    data: TenderBidPlanRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    plan_status = data.plan_status.strip().casefold()
    if plan_status not in _ALLOWED_BID_PLAN_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported bid plan status")

    planned_at = _utc_or_now(data.planned_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    lifecycle["bid_plan"] = {
        "plan_status": plan_status,
        "planned_at": planned_at.isoformat(),
        "owner_user_ids": list(data.owner_user_ids or []),
        "milestone_count": data.milestone_count,
        "notes": data.notes,
        "actor_id": current_user.id,
    }
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    event_type = "bid_plan_approved" if plan_status == "approved" else "bid_plan_created"
    payload = build_bid_plan_event_payload(
        plan_status=plan_status,
        planned_at=planned_at,
        owner_user_ids=data.owner_user_ids,
        milestone_count=data.milestone_count,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type=event_type,
        event_payload=payload,
        occurred_at=planned_at,
    )
    if data.owner_user_ids:
        await publish_domain_event(
            db,
            tender_id=tender.id,
            actor_id=current_user.id,
            event_type="bid_team_assigned",
            payload=build_bid_team_assigned_event_payload(
                assigned_at=planned_at,
                owner_user_ids=data.owner_user_ids,
                notes=data.notes,
            ),
            occurred_at=planned_at,
        )
    return TenderLifecycleActionResponse(status="accepted", event_type=event_type, tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/contribution-wave", response_model=TenderLifecycleActionResponse, status_code=202)
async def open_contribution_wave(
    tender_id: int,
    data: ContributionWaveRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    opened_at = _utc_or_now(data.opened_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    lifecycle["contribution_wave"] = {
        "opened_at": opened_at.isoformat(),
        "contribution_count": data.contribution_count,
        "department_count": data.department_count,
        "notes": data.notes,
        "actor_id": current_user.id,
    }
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    payload = build_contribution_wave_event_payload(
        opened_at=opened_at,
        contribution_count=data.contribution_count,
        department_count=data.department_count,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="contribution_request_wave_opened",
        event_payload=payload,
        occurred_at=opened_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="contribution_request_wave_opened", tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/outcome", response_model=TenderLifecycleActionResponse, status_code=202)
async def record_structured_outcome(
    tender_id: int,
    data: TenderOutcomeRecordRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    outcome = data.outcome.strip().casefold()
    if outcome not in _ALLOWED_OUTCOMES:
        raise HTTPException(status_code=400, detail="Unsupported structured outcome")

    recorded_at = _utc_or_now(data.recorded_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    _apply_structured_outcome(
        tender,
        metadata=metadata,
        lifecycle=lifecycle,
        outcome=outcome,
        recorded_at=recorded_at,
        reason_code=data.reason_code,
        notes=data.notes,
        actor_id=current_user.id,
    )

    await db.flush()

    event_type = _event_type_for_structured_outcome(outcome)

    payload = build_terminal_lifecycle_event_payload(
        outcome=outcome,
        recorded_at=recorded_at,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type=event_type,
        event_payload=payload,
        occurred_at=recorded_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type=event_type, tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/coordination-risk", response_model=TenderLifecycleActionResponse, status_code=202)
async def raise_tender_coordination_risk(
    tender_id: int,
    data: TenderCoordinationRiskRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    payload = build_coordination_risk_raised_event_payload(
        occurred_at=occurred_at,
        external_rework_id=data.external_rework_id,
        external_contribution_id=data.external_contribution_id,
        severity=data.severity,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="coordination_risk_raised",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="coordination_risk_raised", tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/coordination-recovery", response_model=TenderLifecycleActionResponse, status_code=202)
async def return_tender_to_coordination(
    tender_id: int,
    data: TenderCoordinationRecoveryRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    payload = build_rework_reescalated_to_coordination_event_payload(
        occurred_at=occurred_at,
        external_rework_id=data.external_rework_id,
        external_contribution_id=data.external_contribution_id,
        severity=data.severity,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="rework_reescalated_to_coordination",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="rework_reescalated_to_coordination", tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/gate-rework", response_model=TenderLifecycleActionResponse, status_code=202)
async def request_tender_gate_rework(
    tender_id: int,
    data: TenderGateLifecycleRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    payload = build_compliance_gate_rework_requested_event_payload(
        occurred_at=occurred_at,
        external_gate_id=data.external_gate_id,
        gate_name=data.gate_name,
        external_rework_id=data.external_rework_id,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="compliance_gate_rework_requested",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="compliance_gate_rework_requested", tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/gate-stop", response_model=TenderLifecycleActionResponse, status_code=202)
async def stop_tender_at_gate(
    tender_id: int,
    data: TenderGateLifecycleRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    recorded_at = _utc_or_now(data.occurred_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    _apply_structured_outcome(
        tender,
        metadata=metadata,
        lifecycle=lifecycle,
        outcome="stopped",
        recorded_at=recorded_at,
        reason_code=data.reason_code,
        notes=data.notes,
        actor_id=current_user.id,
    )
    await db.flush()

    payload = build_tender_stopped_at_gate_event_payload(
        recorded_at=recorded_at,
        external_gate_id=data.external_gate_id,
        gate_name=data.gate_name,
        reason_code=data.reason_code,
        notes=data.notes,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="tender_stopped_at_gate",
        event_payload=payload,
        occurred_at=recorded_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="tender_stopped_at_gate", tender_id=tender.id, payload=payload)


@router.post("/{tender_id}/clarifications", response_model=TenderLifecycleActionResponse, status_code=202)
async def create_tender_clarification(
    tender_id: int,
    data: TenderClarificationCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    clarifications = list(lifecycle.get("clarifications") or [])
    request_id = data.request_id or f"clar-{len(clarifications) + 1}"
    clarification = _upsert_clarification_record(
        lifecycle=lifecycle,
        request_id=request_id,
        payload={
            "status": "requested",
            "request_summary": data.request_summary,
            "deadline_at": data.deadline_at.isoformat() if data.deadline_at else None,
            "source_label": data.source_label,
            "requested_at": occurred_at.isoformat(),
            "updated_at": occurred_at.isoformat(),
            "actor_id": current_user.id,
        },
    )
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    payload = build_clarification_event_payload(
        request_id=request_id,
        status="requested",
        occurred_at=occurred_at,
        request_summary=data.request_summary,
        deadline_at=data.deadline_at,
        source_label=data.source_label,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="clarification_requested",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="clarification_requested", tender_id=tender.id, payload={**payload, "clarification": clarification})


@router.post("/{tender_id}/clarifications/{clarification_id}/draft", response_model=TenderLifecycleActionResponse, status_code=202)
async def draft_tender_clarification_response(
    tender_id: int,
    clarification_id: str,
    data: TenderClarificationUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    clarification = _upsert_clarification_record(
        lifecycle=lifecycle,
        request_id=clarification_id,
        payload={
            "status": "response_drafted",
            "response_summary": data.response_summary,
            "source_label": data.source_label,
            "updated_at": occurred_at.isoformat(),
            "actor_id": current_user.id,
        },
        allow_create=False,
    )
    if clarification is None:
        raise HTTPException(status_code=404, detail="Clarification not found")
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    payload = build_clarification_event_payload(
        request_id=clarification_id,
        status="response_drafted",
        occurred_at=occurred_at,
        response_summary=data.response_summary,
        source_label=data.source_label,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="clarification_response_drafted",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="clarification_response_drafted", tender_id=tender.id, payload={**payload, "clarification": clarification})


@router.post("/{tender_id}/clarifications/{clarification_id}/submit", response_model=TenderLifecycleActionResponse, status_code=202)
async def submit_tender_clarification_response(
    tender_id: int,
    clarification_id: str,
    data: TenderClarificationUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    clarification = _upsert_clarification_record(
        lifecycle=lifecycle,
        request_id=clarification_id,
        payload={
            "status": "submitted",
            "response_summary": data.response_summary,
            "source_label": data.source_label,
            "submitted_at": occurred_at.isoformat(),
            "updated_at": occurred_at.isoformat(),
            "actor_id": current_user.id,
        },
        allow_create=False,
    )
    if clarification is None:
        raise HTTPException(status_code=404, detail="Clarification not found")
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    payload = build_clarification_event_payload(
        request_id=clarification_id,
        status="submitted",
        occurred_at=occurred_at,
        response_summary=data.response_summary,
        source_label=data.source_label,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="clarification_submitted",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="clarification_submitted", tender_id=tender.id, payload={**payload, "clarification": clarification})


@router.post("/{tender_id}/clarifications/{clarification_id}/close", response_model=TenderLifecycleActionResponse, status_code=202)
async def close_tender_clarification(
    tender_id: int,
    clarification_id: str,
    data: TenderClarificationUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tender = await check_tender_access(tender_id, current_user, db)
    occurred_at = _utc_or_now(data.occurred_at)
    metadata, lifecycle = _clone_lifecycle_metadata(tender)
    clarification = _upsert_clarification_record(
        lifecycle=lifecycle,
        request_id=clarification_id,
        payload={
            "status": "closed",
            "response_summary": data.response_summary,
            "source_label": data.source_label,
            "closed_at": occurred_at.isoformat(),
            "updated_at": occurred_at.isoformat(),
            "actor_id": current_user.id,
        },
        allow_create=False,
    )
    if clarification is None:
        raise HTTPException(status_code=404, detail="Clarification not found")
    _store_lifecycle_metadata(tender, metadata=metadata, lifecycle=lifecycle)
    await db.flush()

    payload = build_clarification_event_payload(
        request_id=clarification_id,
        status="closed",
        occurred_at=occurred_at,
        response_summary=data.response_summary,
        source_label=data.source_label,
    )
    await sync_tender_and_publish_event(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
        event_type="clarification_closed",
        event_payload=payload,
        occurred_at=occurred_at,
    )
    return TenderLifecycleActionResponse(status="accepted", event_type="clarification_closed", tender_id=tender.id, payload={**payload, "clarification": clarification})




