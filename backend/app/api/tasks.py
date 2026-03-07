"""
TenderWriter — Tasks API

Endpoints for managing background tasks.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from celery.result import AsyncResult

from app.celery import celery_app
from app.api.auth import get_current_user, UserResponse

router = APIRouter()


class TaskResponse(BaseModel):
    task_id: str
    status: str
    result: Any | None = None
    error: str | None = None


class IndexDocumentRequest(BaseModel):
    document_id: int


class GenerateSectionRequest(BaseModel):
    proposal_id: int
    section_id: int
    prompt: str | None = None


class ExportPdfRequest(BaseModel):
    proposal_id: int


@router.post("/index-document", response_model=TaskResponse)
async def start_index_document(
    request: IndexDocumentRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Start indexing a document in background."""
    from app.tasks import index_document_task
    
    task = index_document_task.delay(request.document_id)
    
    return TaskResponse(
        task_id=task.id,
        status=task.status,
    )


@router.post("/generate-section", response_model=TaskResponse)
async def start_generate_section(
    request: GenerateSectionRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Start generating a proposal section in background."""
    from app.tasks import generate_proposal_section_task
    
    task = generate_proposal_section_task.delay(
        request.proposal_id,
        request.section_id,
        request.prompt,
    )
    
    return TaskResponse(
        task_id=task.id,
        status=task.status,
    )


@router.post("/export-pdf", response_model=TaskResponse)
async def start_export_pdf(
    request: ExportPdfRequest,
    current_user: UserResponse = Depends(get_current_user),
):
    """Start PDF export in background."""
    from app.tasks import export_proposal_pdf_task
    
    task = export_proposal_pdf_task.delay(request.proposal_id)
    
    return TaskResponse(
        task_id=task.id,
        status=task.status,
    )


@router.get("/status/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Get the status of a background task."""
    task_result = AsyncResult(task_id, app=celery_app)
    
    return TaskResponse(
        task_id=task_id,
        status=task_result.status,
        result=task_result.result if task_result.ready() else None,
        error=str(task_result.info) if task_result.failed() else None,
    )


@router.post("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    """Cancel a running task."""
    celery_app.control.revoke(task_id, terminate=True)
    
    return {"message": "Task cancellation requested", "task_id": task_id}


@router.get("/health")
async def celery_health():
    """Check Celery worker health."""
    from app.tasks import health_check
    
    task = health_check.delay()
    result = AsyncResult(task.id, app=celery_app)
    
    return {
        "workers": "healthy" if result.get(timeout=5) else "unhealthy",
        "redis": "connected",
    }
