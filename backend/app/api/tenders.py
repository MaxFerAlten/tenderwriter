"""
TenderWriter — Tenders API

CRUD endpoints for managing tenders (RFPs/ITTs).
Includes document upload + ingestion trigger and requirement management.
All endpoints are protected with JWT auth and granular RBAC.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Annotated, Any
import traceback
import logging

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from minio import Minio
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models import (
    ConsolidatedRequirement,
    RequirementReview,
    RequirementRelation,
    RequirementRelationReview,
    Tender,
    TenderRequirement,
    TenderStatus,
    ComplianceStatus,
    TenderPermission,
    RequirementCandidate,
    RequirementExtractionRun,
    Document,
    IngestionStatus,
)
from app.api.auth import get_current_user, UserResponse
from app.utils.naming import get_tender_upload_path
from app.services.chat import ensure_official_chat_room, sync_chat_members_from_tender_permissions
from app.ingestion.observability import extract_ingestion_observability
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
from app.services.compliance_observability import (
    ComplianceRequirementCoverage,
    build_compliance_requirement_coverage,
    sync_requirement_compliance_and_gate,
)
from app.services.requirement_candidates import (
    list_staged_requirement_candidate_runs,
    stage_extracted_requirement_candidates,
)
from app.services.requirement_consolidation import (
    list_consolidated_requirements,
    list_requirement_relations,
    rebuild_consolidated_requirements_from_staging,
)
from app.services.requirement_review import (
    apply_requirement_review,
    get_consolidated_requirement_for_tender,
    list_consolidated_requirements_for_review,
)
from app.services.requirement_relation_review import (
    apply_requirement_relation_review,
    get_requirement_relation_for_tender,
    list_requirement_relations_for_review,
)
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


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_url: str
    doc_type: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    ingestion_status: str
    ingestion_progress: float | None = 0.0
    chunk_count: int
    error_message: str | None = None
    source_kind: str | None = None
    ingestion_started_at: datetime | None = None
    ingestion_completed_at: datetime | None = None
    ingestion_job_id: str | None = None
    created_at: datetime | None = None
    metadata_json: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class RequirementResponse(BaseModel):
    id: int
    requirement_text: str
    category: str | None
    priority: str
    compliance_status: str
    mapped_section_id: int | None = None
    mapped_section_title: str | None = None
    coverage_source: str = "legacy"

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
    ingestion_status: str | None = None
    ingestion_progress: float | None = 0.0

    model_config = {"from_attributes": True}


class TenderDetailResponse(TenderResponse):
    requirements: list[RequirementResponse] = []


class RequirementCandidateResponse(BaseModel):
    id: int
    candidate_position: int
    summary_text: str
    normalized_text: str
    category: str | None = None
    priority: str
    confidence: float | None = None
    source_document_ref: str | None = None
    source_reference: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RequirementExtractionRunResponse(BaseModel):
    id: int
    source_document_ref: str | None = None
    filename: str | None = None
    extraction_method: str
    candidate_count: int
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None
    candidates: list[RequirementCandidateResponse] = []

    model_config = {"from_attributes": True}


class RequirementExtractionRunListResponse(BaseModel):
    items: list[RequirementExtractionRunResponse]
    total_runs: int


class ConsolidatedRequirementResponse(BaseModel):
    id: int
    canonical_text: str
    normalized_text: str
    category: str | None = None
    priority: str
    confidence: float | None = None
    source_count: int
    consolidation_method: str
    review_state: str
    graph_state: str
    parent_requirement_id: int | None = None
    parent_requirement_key: str | None = None
    applicability: dict[str, Any] | None = None
    conditions: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsolidatedRequirementListResponse(BaseModel):
    items: list[ConsolidatedRequirementResponse]
    total_items: int


class ConsolidatedRequirementEditRequest(BaseModel):
    canonical_text: str | None = None
    category: str | None = None
    priority: str | None = None
    parent_requirement_key: str | None = None
    applicability: dict[str, Any] | None = None
    conditions: list[str] | None = None
    exceptions: list[str] | None = None


class ConsolidatedRequirementSplitRequest(ConsolidatedRequirementEditRequest):
    canonical_text: str


class ConsolidatedRequirementReviewRequest(BaseModel):
    action: str
    notes: str | None = None
    edit: ConsolidatedRequirementEditRequest | None = None
    target_requirement_id: int | None = None
    split_requirements: list[ConsolidatedRequirementSplitRequest] = Field(default_factory=list)


class RequirementReviewResponse(BaseModel):
    id: int
    action: str
    previous_review_state: str | None = None
    new_review_state: str
    notes: str | None = None
    actor_id: int | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConsolidatedRequirementReviewActionResponse(BaseModel):
    requirement: ConsolidatedRequirementResponse
    review: RequirementReviewResponse


class RequirementRelationResponse(BaseModel):
    id: int
    source_requirement_id: int
    source_requirement_text: str
    target_requirement_id: int
    target_requirement_text: str
    relation_type: str
    confidence: float | None = None
    review_state: str
    graph_state: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None


class RequirementRelationListResponse(BaseModel):
    items: list[RequirementRelationResponse]
    total_items: int


class RequirementRelationEditRequest(BaseModel):
    source_requirement_id: int | None = None
    target_requirement_id: int | None = None
    relation_type: str | None = None
    confidence: float | None = None


class RequirementRelationReviewRequest(BaseModel):
    action: str
    notes: str | None = None
    edit: RequirementRelationEditRequest | None = None


class RequirementRelationReviewResponse(BaseModel):
    id: int
    action: str
    previous_review_state: str | None = None
    new_review_state: str
    notes: str | None = None
    actor_id: int | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class RequirementRelationReviewActionResponse(BaseModel):
    relation: RequirementRelationResponse
    review: RequirementRelationReviewResponse


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
            selectinload(Tender.consolidated_requirements),
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

    ing_status = None
    ing_progress = 0.0
    if 'documents' not in insp.unloaded and tender.documents:
        # Diagnostic print
        # print(f"Processing documents for tender {tender.id}: {len(tender.documents)}")
        statuses = [d.ingestion_status.value if hasattr(d.ingestion_status, 'value') else d.ingestion_status for d in tender.documents]
        progress_vals = [d.ingestion_progress or 0.0 for d in tender.documents]
        
        if "processing" in statuses:
            ing_status = "processing"
            # Return mean progress of processing documents
            processing_vals = [d.ingestion_progress or 0.0 for d in tender.documents if d.ingestion_status == IngestionStatus.PROCESSING]
            ing_progress = sum(processing_vals) / len(processing_vals) if processing_vals else 0.0
        elif "completed" in statuses:
            ing_status = "completed"
            ing_progress = 100.0
        elif "failed" in statuses:
            ing_status = "failed"
            ing_progress = 100.0
        elif "pending" in statuses:
            ing_status = "pending"
            ing_progress = 0.0

    # Coerce tags to clean list of strings
    clean_tags = [str(t) for t in (tender.tags or []) if t is not None]
    
    # Coerce metadata safely
    metadata_raw = tender.metadata_json if isinstance(tender.metadata_json, dict) else {}
    lifecycle = metadata_raw.get("lifecycle")
    if lifecycle is not None and not isinstance(lifecycle, dict):
        lifecycle = {"raw_value": str(lifecycle)}

    return TenderResponse(
        id=tender.id,
        title=tender.title,
        client=tender.client,
        description=tender.description,
        deadline=tender.deadline,
        status=tender.status.value if hasattr(tender.status, 'value') else str(tender.status or "draft"),
        category=tender.category,
        tags=clean_tags,
        budget_estimate=tender.budget_estimate,
        created_at=tender.created_at,
        requirement_count=req_count,
        proposal_id=prop_id,
        created_by=tender.created_by,
        created_by_name=creator_name,
        lifecycle_metadata=lifecycle,
        ingestion_status=ing_status,
        ingestion_progress=ing_progress,
    )

def _safe_tender_to_response(tender: Tender) -> TenderResponse | None:
    try:
        return _tender_to_response(tender)
    except Exception:
        print(f"FAILED MAPPING FOR TENDER {tender.id}:")
        traceback.print_exc()
        return None


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
        coverage_source="legacy",
    )


def _coverage_requirement_to_response(requirement: ComplianceRequirementCoverage) -> RequirementResponse:
    return RequirementResponse(
        id=requirement.id,
        requirement_text=requirement.requirement_text,
        category=requirement.category,
        priority=requirement.priority,
        compliance_status=requirement.compliance_status.value,
        mapped_section_id=requirement.proposal_section_id,
        mapped_section_title=requirement.proposal_section_title,
        coverage_source=requirement.coverage_source,
    )


def _requirement_candidate_to_response(
    candidate: RequirementCandidate,
) -> RequirementCandidateResponse:
    return RequirementCandidateResponse(
        id=candidate.id,
        candidate_position=candidate.candidate_position,
        summary_text=candidate.summary_text,
        normalized_text=candidate.normalized_text,
        category=candidate.category,
        priority=candidate.priority,
        confidence=candidate.confidence,
        source_document_ref=candidate.source_document_ref,
        source_reference=candidate.source_reference,
        created_at=candidate.created_at,
    )


def _requirement_extraction_run_to_response(
    extraction_run: RequirementExtractionRun,
) -> RequirementExtractionRunResponse:
    ordered_candidates = sorted(
        list(extraction_run.candidates or []),
        key=lambda candidate: (candidate.candidate_position or 0, candidate.id or 0),
    )
    return RequirementExtractionRunResponse(
        id=extraction_run.id,
        source_document_ref=extraction_run.source_document_ref,
        filename=extraction_run.filename,
        extraction_method=extraction_run.extraction_method,
        candidate_count=extraction_run.candidate_count,
        metadata_json=dict(extraction_run.metadata_json or {}),
        created_at=extraction_run.created_at,
        candidates=[_requirement_candidate_to_response(candidate) for candidate in ordered_candidates],
    )


def _consolidated_requirement_to_response(
    requirement: ConsolidatedRequirement,
) -> ConsolidatedRequirementResponse:
    return ConsolidatedRequirementResponse(
        id=requirement.id,
        canonical_text=requirement.canonical_text,
        normalized_text=requirement.normalized_text,
        category=requirement.category,
        priority=requirement.priority,
        confidence=requirement.confidence,
        source_count=requirement.source_count,
        consolidation_method=requirement.consolidation_method,
        review_state=requirement.review_state,
        graph_state=str(requirement.graph_state or "active"),
        parent_requirement_id=requirement.parent_requirement_id,
        parent_requirement_key=requirement.parent_requirement_key,
        applicability=dict(requirement.applicability or {}),
        conditions=list(requirement.conditions or []),
        exceptions=list(requirement.exceptions or []),
        metadata_json=dict(requirement.metadata_json or {}),
        created_at=requirement.created_at,
    )


def _requirement_review_to_response(
    review: RequirementReview,
) -> RequirementReviewResponse:
    return RequirementReviewResponse(
        id=review.id,
        action=review.action,
        previous_review_state=review.previous_review_state,
        new_review_state=review.new_review_state,
        notes=review.notes,
        actor_id=review.actor_id,
        metadata_json=dict(review.metadata_json or {}),
        created_at=review.created_at,
    )


def _requirement_relation_to_response(
    relation: RequirementRelation,
) -> RequirementRelationResponse:
    source_requirement = relation.source_requirement
    target_requirement = relation.target_requirement
    return RequirementRelationResponse(
        id=relation.id,
        source_requirement_id=relation.source_requirement_id,
        source_requirement_text=getattr(source_requirement, "canonical_text", "") or "",
        target_requirement_id=relation.target_requirement_id,
        target_requirement_text=getattr(target_requirement, "canonical_text", "") or "",
        relation_type=relation.relation_type,
        confidence=relation.confidence,
        review_state=str(relation.review_state or "pending"),
        graph_state=str(relation.graph_state or "active"),
        metadata_json=dict(relation.metadata_json or {}),
        created_at=relation.created_at,
    )


def _requirement_relation_review_to_response(
    review: RequirementRelationReview,
) -> RequirementRelationReviewResponse:
    return RequirementRelationReviewResponse(
        id=review.id,
        action=review.action,
        previous_review_state=review.previous_review_state,
        new_review_state=review.new_review_state,
        notes=review.notes,
        actor_id=review.actor_id,
        metadata_json=dict(review.metadata_json or {}),
        created_at=review.created_at,
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
        selectinload(Tender.documents),
        selectinload(Tender.requirements),
    )
    # logger.info("Building tender list query", status=status, category=category, search=search)

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

    try:
        # Count total - use a clean query for counting to avoid subquery issues with load options
        count_q = select(func.count(Tender.id))
        if current_user.role != "admin":
             permitted_subq = select(TenderPermission.tender_id).where(TenderPermission.user_id == current_user.id)
             count_q = count_q.where(or_(Tender.created_by == current_user.id, Tender.id.in_(permitted_subq)))
        
        if status: count_q = count_q.where(Tender.status == status)
        if category: count_q = count_q.where(Tender.category == category)
        if search:
            escaped_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            count_q = count_q.where(Tender.title.ilike(f"%{escaped_search}%", escape="\\"))
            
        total = (await db.execute(count_q)).scalar() or 0

        # Fetch page
        query = query.order_by(Tender.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        tenders = result.scalars().all()
    except Exception as e:
        print("ERROR IN list_tenders DB EXECUTION:")
        traceback.print_exc()
        raise e

    # items = [_tender_to_response(t) for t in tenders]
    items = []
    for t in tenders:
        resp = _safe_tender_to_response(t)
        if resp:
            items.append(resp)

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
        requirements=[
            _coverage_requirement_to_response(requirement)
            for requirement in build_compliance_requirement_coverage(tender)
        ],
    )


@router.get(
    "/{tender_id}/requirement-candidates",
    response_model=RequirementExtractionRunListResponse,
)
async def get_tender_requirement_candidates(
    tender_id: int,
    limit_runs: int = Query(default=5, ge=1, le=20),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return recent staged requirement extraction runs for a tender."""

    await check_tender_access(tender_id, current_user, db)
    extraction_runs = await list_staged_requirement_candidate_runs(
        db,
        tender_id=tender_id,
        limit_runs=limit_runs,
    )
    return RequirementExtractionRunListResponse(
        items=[_requirement_extraction_run_to_response(run) for run in extraction_runs],
        total_runs=len(extraction_runs),
    )


@router.get(
    "/{tender_id}/consolidated-requirements",
    response_model=ConsolidatedRequirementListResponse,
)
async def get_tender_consolidated_requirements(
    tender_id: int,
    graph_state: Annotated[str | None, Query()] = "active",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return persisted consolidated requirements for a tender."""

    await check_tender_access(tender_id, current_user, db)
    requirements = await list_consolidated_requirements(
        db,
        tender_id=tender_id,
        graph_state=graph_state,
    )
    return ConsolidatedRequirementListResponse(
        items=[_consolidated_requirement_to_response(item) for item in requirements],
        total_items=len(requirements),
    )


@router.get(
    "/{tender_id}/consolidated-requirements/review-queue",
    response_model=ConsolidatedRequirementListResponse,
)
async def get_tender_consolidated_requirement_review_queue(
    tender_id: int,
    review_state: str | None = Query(default="pending"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return consolidated requirements ordered for review triage."""

    await check_tender_access(tender_id, current_user, db)
    requirements = await list_consolidated_requirements_for_review(
        db,
        tender_id=tender_id,
        review_state=review_state,
        limit=limit,
    )
    return ConsolidatedRequirementListResponse(
        items=[_consolidated_requirement_to_response(item) for item in requirements],
        total_items=len(requirements),
    )


@router.get(
    "/{tender_id}/consolidated-requirements/relations",
    response_model=RequirementRelationListResponse,
)
async def get_tender_consolidated_requirement_relations(
    tender_id: int,
    relation_type: str | None = Query(default=None),
    graph_state: Annotated[str | None, Query()] = "active",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return persisted requirement relations for a tender."""

    await check_tender_access(tender_id, current_user, db)
    relations = await list_requirement_relations(
        db,
        tender_id=tender_id,
        relation_type=relation_type,
        graph_state=graph_state,
    )
    return RequirementRelationListResponse(
        items=[_requirement_relation_to_response(item) for item in relations],
        total_items=len(relations),
    )


@router.get(
    "/{tender_id}/consolidated-requirements/relations/review-queue",
    response_model=RequirementRelationListResponse,
)
async def get_tender_consolidated_requirement_relation_review_queue(
    tender_id: int,
    review_state: str | None = Query(default="pending"),
    relation_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return inferred requirement relations ordered for review triage."""

    await check_tender_access(tender_id, current_user, db)
    relations = await list_requirement_relations_for_review(
        db,
        tender_id=tender_id,
        review_state=review_state,
        relation_type=relation_type,
        limit=limit,
    )
    return RequirementRelationListResponse(
        items=[_requirement_relation_to_response(item) for item in relations],
        total_items=len(relations),
    )


@router.post(
    "/{tender_id}/consolidated-requirements/rebuild",
    response_model=ConsolidatedRequirementListResponse,
    status_code=202,
)
async def rebuild_tender_consolidated_requirements(
    tender_id: int,
    limit_runs: int = Query(default=5, ge=1, le=20),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rebuild persisted consolidated requirements from staged candidates."""

    await check_tender_access(tender_id, current_user, db)
    requirements = await rebuild_consolidated_requirements_from_staging(
        db,
        tender_id=tender_id,
        limit_runs=limit_runs,
    )
    return ConsolidatedRequirementListResponse(
        items=[_consolidated_requirement_to_response(item) for item in requirements],
        total_items=len(requirements),
    )


@router.post(
    "/{tender_id}/consolidated-requirements/{requirement_id}/review",
    response_model=ConsolidatedRequirementReviewActionResponse,
    status_code=202,
)
async def review_tender_consolidated_requirement(
    tender_id: int,
    requirement_id: int,
    data: ConsolidatedRequirementReviewRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a review decision to a consolidated requirement."""

    await check_tender_access(tender_id, current_user, db)
    requirement = await get_consolidated_requirement_for_tender(
        db,
        tender_id=tender_id,
        requirement_id=requirement_id,
    )
    if requirement is None:
        raise HTTPException(status_code=404, detail="Consolidated requirement not found")

    target_requirement = None
    if data.target_requirement_id is not None:
        target_requirement = await get_consolidated_requirement_for_tender(
            db,
            tender_id=tender_id,
            requirement_id=data.target_requirement_id,
        )
        if target_requirement is None:
            raise HTTPException(status_code=404, detail="Target consolidated requirement not found")

    review_kwargs: dict[str, Any] = {
        "requirement": requirement,
        "actor_id": current_user.id,
        "action": data.action,
        "notes": data.notes,
    }
    if data.edit is not None:
        review_kwargs["edit_payload"] = data.edit.model_dump(exclude_none=True)
    if target_requirement is not None:
        review_kwargs["target_requirement"] = target_requirement
    if data.split_requirements:
        review_kwargs["split_payloads"] = [
            item.model_dump(exclude_none=True) for item in data.split_requirements
        ]

    try:
        updated_requirement, review = await apply_requirement_review(
            db,
            **review_kwargs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConsolidatedRequirementReviewActionResponse(
        requirement=_consolidated_requirement_to_response(updated_requirement),
        review=_requirement_review_to_response(review),
    )


@router.post(
    "/{tender_id}/consolidated-requirements/relations/{relation_id}/review",
    response_model=RequirementRelationReviewActionResponse,
    status_code=202,
)
async def review_tender_consolidated_requirement_relation(
    tender_id: int,
    relation_id: int,
    data: RequirementRelationReviewRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a review decision to an inferred requirement relation."""

    await check_tender_access(tender_id, current_user, db)
    relation = await get_requirement_relation_for_tender(
        db,
        tender_id=tender_id,
        relation_id=relation_id,
    )
    if relation is None:
        raise HTTPException(status_code=404, detail="Requirement relation not found")

    relation_edit_payload = data.edit.model_dump(exclude_none=True) if data.edit is not None else None
    if relation_edit_payload:
        for requirement_key in ("source_requirement_id", "target_requirement_id"):
            requirement_id = relation_edit_payload.get(requirement_key)
            if requirement_id is None:
                continue
            related_requirement = await get_consolidated_requirement_for_tender(
                db,
                tender_id=tender_id,
                requirement_id=int(requirement_id),
            )
            if related_requirement is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Relation {requirement_key} requirement not found",
                )

    relation_review_kwargs: dict[str, Any] = {
        "relation": relation,
        "actor_id": current_user.id,
        "action": data.action,
        "notes": data.notes,
    }
    if relation_edit_payload:
        relation_review_kwargs["edit_payload"] = relation_edit_payload

    try:
        updated_relation, review = await apply_requirement_relation_review(
            db,
            **relation_review_kwargs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RequirementRelationReviewActionResponse(
        relation=_requirement_relation_to_response(updated_relation),
        review=_requirement_relation_review_to_response(review),
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
    Upload a tender document (PDF/DOCX). RBAC-checked.
    Creates a Document record and enqueues the ingestion task.
    """
    tender = await check_tender_access(tender_id, current_user, db)
    
    # Restrict uploads for finalized tenders
    if tender.status in [TenderStatus.SUBMITTED, TenderStatus.WON, TenderStatus.LOST, TenderStatus.CANCELLED]:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot upload documents to a tender with status '{tender.status.value}'"
        )

    # 1. Create Document record in PENDING state
    doc = Document(
        filename=file.filename or "unknown",
        file_url="",  # Will update after upload
        doc_type="tender",
        file_size=file.size or 0,
        mime_type=file.content_type,
        ingestion_status=IngestionStatus.PENDING,
        uploaded_by=current_user.id,
        tender_id=tender.id,
        source_kind="upload",
    )
    db.add(doc)
    await db.flush()

    # 2. Upload to MinIO
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

    # 3. Update Document with storage metadata
    doc.storage_bucket = bucket_name
    doc.storage_object_name = object_name
    doc.file_url = f"minio://{bucket_name}/{object_name}"
    await db.flush()

    # 4. Enqueue Ingestion Task
    from app.tasks import index_document_task
    task = index_document_task.delay(doc.id)

    # 5. Save tracking information
    doc.ingestion_job_id = task.id
    
    await db.commit()

    return {
        "message": "Document uploaded and ingestion queued successfully",
        "tender_id": tender_id,
        "document_id": doc.id,
        "task_id": task.id,
        "filename": file.filename,
        "status": "queued",
    }




@router.get("/{tender_id}/documents", response_model=list[DocumentResponse])
async def list_tender_documents(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all documents for a tender."""
    await check_tender_access(tender_id, current_user, db)
    result = await db.execute(
        select(Document)
        .where(Document.tender_id == tender_id)
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{tender_id}/documents/{document_id}", response_model=DocumentResponse)
async def get_tender_document(
    tender_id: int,
    document_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of a specific tender document."""
    await check_tender_access(tender_id, current_user, db)
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tender_id == tender_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found for this tender")
    return doc


@router.get("/{tender_id}/documents/{document_id}/stream")
async def stream_document_status(
    tender_id: int,
    document_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """SSE endpoint to stream document ingestion status updates."""
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    from app.db.database import async_session_factory

    await check_tender_access(tender_id, current_user, db)

    async def event_generator():
        async_session = async_session_factory
        while True:
            async with async_session() as session:
                result = await session.execute(
                    select(Document).where(
                        Document.id == document_id,
                        Document.tender_id == tender_id
                    )
                )
                doc = result.scalar_one_or_none()
                if not doc:
                    yield "event: error\ndata: {\"error\": \"Document not found\"}\n\n"
                    break

                status_val = doc.ingestion_status.value if hasattr(doc.ingestion_status, 'value') else doc.ingestion_status
                metadata_json = dict(doc.metadata_json or {}) if isinstance(doc.metadata_json, dict) else {}
                observability = extract_ingestion_observability(metadata_json)
                payload = {
                    "id": doc.id,
                    "status": status_val,
                    "progress": doc.ingestion_progress,
                    "error_message": doc.error_message,
                    "metadata_json": metadata_json,
                    "current_stage": observability.get("current_stage"),
                    "current_stage_label": observability.get("current_stage_label"),
                    "current_stage_status": observability.get("current_stage_status"),
                    "current_stage_detail": observability.get("current_stage_detail"),
                }
                yield f"data: {json.dumps(payload)}\n\n"

                if status_val in ("completed", "failed"):
                    break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/{tender_id}/activate", response_model=TenderResponse)
async def activate_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly activate a tender (transits from DRAFT to ACTIVE).
    Opens the chat room and ensures background tasks are initialized.
    """
    # Use check_tender_access which eager loads proposals for response mapping
    tender = await check_tender_access(tender_id, current_user, db)
    
    if tender.status != TenderStatus.DRAFT:
        raise HTTPException(
            status_code=400,
            detail=f"Tender cannot be activated from status '{tender.status.value}'"
        )
        
    # Lock for update
    result = await db.execute(select(Tender).where(Tender.id == tender_id).with_for_update())
    tender_db = result.scalar_one()

    tender_db.status = TenderStatus.ACTIVE
    await db.flush()
    await db.refresh(tender_db)

    # Note: Using tender_db but checking the pre-loaded tender to keep _tender_to_response happy
    # since _tender_to_response checks lazy loads on the parameter passed.
    tender.status = tender_db.status

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

    await publish_tender_sync(
        db,
        tender_id=tender.id,
        actor_id=current_user.id,
    )

    return _tender_to_response(tender)


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



