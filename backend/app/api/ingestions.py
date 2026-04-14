"""
TenderWriter — Ingestions Monitor API
"""

from typing import Any
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc, String
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.api.auth import get_current_user, UserResponse
from app.ingestion.observability import extract_ingestion_observability
from app.models import Document, Tender, IngestionStatus

router = APIRouter()

class IngestionMonitorRecord(BaseModel):
    id: int
    filename: str
    status: str
    progress: float
    error_message: str | None = None
    created_at: datetime
    tender_id: int | None = None
    tender_title: str | None = None
    uploaded_by: int | None = None
    metadata_json: dict[str, Any] | None = None
    current_stage: str | None = None
    current_stage_label: str | None = None
    current_stage_status: str | None = None
    current_stage_detail: str | None = None

    model_config = {"from_attributes": True}

class IngestionStats(BaseModel):
    total: int
    processing: int
    completed: int
    failed: int
    success_rate: float

@router.get("", response_model=list[IngestionMonitorRecord])
async def list_ingestions(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List most recent document ingestions across all tenders."""
    query = (
        select(Document, Tender.title.label("tender_title"))
        .outerjoin(Tender, Document.tender_id == Tender.id)
        .order_by(desc(Document.created_at))
        .limit(limit)
    )
    
    if status:
        # Map frontend lowercase status back to uppercase for DB if DB uses uppercase
        query = query.where(func.upper(func.cast(Document.ingestion_status, String)) == status.upper())
        
    result = await db.execute(query)
    records = []
    for doc, tender_title in result:
        metadata_json = dict(doc.metadata_json or {}) if isinstance(doc.metadata_json, dict) else {}
        observability = extract_ingestion_observability(metadata_json)
        records.append(IngestionMonitorRecord(
            id=doc.id,
            filename=doc.filename,
            status=doc.ingestion_status.value if hasattr(doc.ingestion_status, 'value') else str(doc.ingestion_status).lower(),
            progress=doc.ingestion_progress or 0.0,
            error_message=doc.error_message,
            created_at=doc.created_at,
            tender_id=doc.tender_id,
            tender_title=tender_title,
            uploaded_by=doc.uploaded_by,
            metadata_json=metadata_json,
            current_stage=observability.get("current_stage"),
            current_stage_label=observability.get("current_stage_label"),
            current_stage_status=observability.get("current_stage_status"),
            current_stage_detail=observability.get("current_stage_detail"),
        ))
    
    return records

@router.get("/stats", response_model=IngestionStats)
async def get_ingestion_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate statistics for document ingestions."""
    # This could be highly optimized with a single group-by query
    query = select(Document.ingestion_status, func.count(Document.id)).group_by(Document.ingestion_status)
    result = await db.execute(query)
    
    counts = {s.value: 0 for s in IngestionStatus}
    total = 0
    for status, count in result:
        status_key = status.value if hasattr(status, 'value') else str(status).lower()
        if status_key in counts:
            counts[status_key] += count
        else:
            counts[status_key] = count
        total += count
        
    success_rate = (counts["completed"] / total * 100) if total > 0 else 0.0
    
    return IngestionStats(
        total=total,
        processing=counts["processing"],
        completed=counts["completed"],
        failed=counts["failed"],
        success_rate=round(success_rate, 1)
    )
