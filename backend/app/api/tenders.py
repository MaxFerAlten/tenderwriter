"""
TenderWriter — Tenders API

CRUD endpoints for managing tenders (RFPs/ITTs).
Includes document upload + ingestion trigger and requirement management.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from minio import Minio
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models import Tender, TenderRequirement, TenderStatus, ComplianceStatus

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

    model_config = {"from_attributes": True}


class TenderDetailResponse(TenderResponse):
    requirements: list[RequirementResponse] = []


class TenderListResponse(BaseModel):
    items: list[TenderResponse]
    total: int


# ── Routes ──


@router.get("", response_model=TenderListResponse)
async def list_tenders(
    status: TenderStatus | None = None,
    category: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List tenders with filtering, search, and pagination."""
    query = select(Tender)

    if status:
        query = query.where(Tender.status == status)
    if category:
        query = query.where(Tender.category == category)
    if search:
        query = query.where(Tender.title.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Fetch page
    query = query.order_by(Tender.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    tenders = result.scalars().all()

    items = [
        TenderResponse(
            id=t.id,
            title=t.title,
            client=t.client,
            description=t.description,
            deadline=t.deadline,
            status=t.status.value if t.status else "draft",
            category=t.category,
            tags=t.tags or [],
            budget_estimate=t.budget_estimate,
            created_at=t.created_at,
        )
        for t in tenders
    ]

    return TenderListResponse(items=items, total=total)


@router.post("", response_model=TenderResponse, status_code=201)
async def create_tender(
    data: TenderCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new tender."""
    tender = Tender(
        title=data.title,
        client=data.client,
        description=data.description,
        deadline=data.deadline,
        category=data.category,
        tags=data.tags,
        budget_estimate=data.budget_estimate,
        status=TenderStatus.DRAFT,
    )
    db.add(tender)
    await db.flush()
    await db.refresh(tender)

    return TenderResponse(
        id=tender.id,
        title=tender.title,
        client=tender.client,
        description=tender.description,
        deadline=tender.deadline,
        status=tender.status.value,
        category=tender.category,
        tags=tender.tags or [],
        budget_estimate=tender.budget_estimate,
        created_at=tender.created_at,
    )


@router.get("/{tender_id}", response_model=TenderDetailResponse)
async def get_tender(tender_id: int, db: AsyncSession = Depends(get_db)):
    """Get a tender by ID with its requirements."""
    result = await db.execute(
        select(Tender)
        .where(Tender.id == tender_id)
        .options(selectinload(Tender.requirements))
    )
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    return TenderDetailResponse(
        id=tender.id,
        title=tender.title,
        client=tender.client,
        description=tender.description,
        deadline=tender.deadline,
        status=tender.status.value,
        category=tender.category,
        tags=tender.tags or [],
        budget_estimate=tender.budget_estimate,
        created_at=tender.created_at,
        requirement_count=len(tender.requirements),
        requirements=[
            RequirementResponse(
                id=r.id,
                requirement_text=r.requirement_text,
                category=r.category,
                priority=r.priority,
                compliance_status=r.compliance_status.value,
            )
            for r in tender.requirements
        ],
    )


@router.put("/{tender_id}", response_model=TenderResponse)
async def update_tender(
    tender_id: int,
    data: TenderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a tender."""
    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tender, key, value)

    await db.flush()
    await db.refresh(tender)

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
    )


@router.delete("/{tender_id}", status_code=204)
async def delete_tender(tender_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a tender and all associated data."""
    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    await db.delete(tender)


@router.post("/{tender_id}/import", status_code=202)
async def import_tender_document(
    tender_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and process a tender document (PDF/DOCX).

    Triggers the ingestion pipeline: parse → extract requirements → index.
    """
    result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

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

    object_name = f"tenders/{tender_id}/{file.filename}"
    
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
    # We need a local path or a way for the pipeline to read from MinIO.
    # For now, let's download it to a temp file for processing, 
    # as the current pipeline implementation likely expects a file path.
    # improvement: The pipeline should ideally handle stream or MinIO URL.
    
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    # Run ingestion in background (or await if fast enough - usually background task)
    # For MVP we await it to see immediate results, but this should be a background task (Celery/Arq)
    rag_engine = request.app.state.rag_engine
    
    # We need to access the pipeline. The RAG engine might not expose it directly 
    # if it's not designed that way. Let's assume we can instantiate it or get it.
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(rag_engine)
    
    try:
        stats = await pipeline.ingest_file(
            file_path=tmp_path,
            document_id=tender_id, # Linking to tender as document ID for now
            doc_type="tender",
            metadata={"original_filename": file.filename}
        )
    finally:
        # Cleanup temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {
        "message": "Document uploaded and ingested successfully",
        "tender_id": tender_id,
        "filename": file.filename,
        "stats": stats,
    }
