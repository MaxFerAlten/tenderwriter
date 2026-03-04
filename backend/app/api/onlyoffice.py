"""
TenderWriter — OnlyOffice Integration API

Provides document serving, callback handling, and RAG indexing
for OnlyOffice Document Server integration.
"""

from __future__ import annotations

import hashlib
import io
import time
import jwt
from datetime import datetime

import httpx
import structlog
from docx import Document as DocxDocument
from docx.shared import Pt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.database import get_db
from app.models import Proposal, ProposalSection, ContentBlock
from app.api.auth import get_current_user, UserResponse

logger = structlog.get_logger()

router = APIRouter()


# ── Schemas ──


class OnlyOfficeConfigResponse(BaseModel):
    """Full configuration for OnlyOffice DocEditor initialization."""
    config: dict
    token: str
    onlyoffice_url: str


# ── Helpers ──


def _build_config_dict(
    doc_key: str, 
    title: str, 
    file_url: str, 
    callback_url: str,
    user_id: str = "guest",
    user_name: str = "TenderWriter User"
) -> dict:
    """Standardize OnlyOffice configuration object structure."""
    return {
        "document": {
            "fileType": "docx",
            "key": doc_key,
            "title": title,
            "url": file_url,
            "permissions": {
                "comment": True,
                "copy": True,
                "download": True,
                "edit": True,
                "print": True,
                "fillForms": True,
                "chat": True,
            }
        },
        "documentType": "word",
        "width": "100%",
        "height": "100%",
        "editorConfig": {
            "callbackUrl": callback_url,
            "lang": "it",
            "mode": "edit",
            "user": {
                "id": user_id,
                "name": user_name,
            },
            "customization": {
                "autosave": True,
                "comments": True,
                "compactHeader": True,
                "compactToolbar": False,
                "feedback": False,
                "forcesave": True,
                "help": True,
                "hideRightMenu": True,
                "hideRulers": False,
                "logo": {
                    "image": "",
                    "visible": False,
                },
                "toolbarNoTabs": False,
            },
        },
    }


def _generate_document_key(proposal_id: int, section_id: int) -> str:
    """Generate a unique document key for OnlyOffice.
    
    OnlyOffice caches documents by key. We include a timestamp
    so that each editing session gets a fresh key.
    """
    raw = f"p{proposal_id}_s{section_id}_{int(time.time())}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


def _generate_library_document_key(block_id: int) -> str:
    """Generate a unique document key for a library block."""
    raw = f"lib_{block_id}_{int(time.time())}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


def _generate_create_document_key() -> str:
    """Generate a unique document key for a new document creation."""
    raw = f"create_{int(time.time())}"
    return hashlib.md5(raw.encode()).hexdigest()[:20]


def _section_content_to_text(content: dict | None) -> str:
    """Extract plain text from section content (TipTap JSON format)."""
    if not content or not isinstance(content, dict):
        return ""
    
    if content.get("type") == "doc" and isinstance(content.get("content"), list):
        paragraphs = []
        for node in content["content"]:
            if isinstance(node, dict) and isinstance(node.get("content"), list):
                text_parts = [c.get("text", "") for c in node["content"] if isinstance(c, dict)]
                paragraphs.append("".join(text_parts))
        return "\n\n".join(paragraphs)
    
    if isinstance(content.get("text"), str):
        return content["text"]
    
    return ""


def _create_docx_from_text(text: str, title: str = "") -> bytes:
    """Create a .docx file from plain text."""
    doc = DocxDocument()
    
    if title:
        doc.add_heading(title, level=1)
    
    if text.strip():
        for paragraph in text.split("\n\n"):
            if paragraph.strip():
                p = doc.add_paragraph(paragraph.strip())
                for run in p.runs:
                    run.font.size = Pt(11)
    else:
        doc.add_paragraph("")
    
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def _extract_text_from_docx(docx_bytes: bytes) -> str:
    """Extract plain text from a .docx file."""
    doc = DocxDocument(io.BytesIO(docx_bytes))
    paragraphs = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            paragraphs.append(paragraph.text)
    return "\n\n".join(paragraphs)


def _text_to_tiptap_content(text: str) -> dict:
    """Convert plain text to TipTap-compatible JSON."""
    return {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": para}],
            }
            for para in text.split("\n\n")
            if para.strip()
        ] or [{"type": "paragraph", "content": [{"type": "text", "text": ""}]}],
    }


# In-memory document store (maps document keys to docx bytes)
# In production, use MinIO, but for MVP this avoids extra complexity
_document_store: dict[str, bytes] = {}
_key_to_section: dict[str, tuple[int, int]] = {}  # key -> (proposal_id, section_id)
_key_to_library_block: dict[str, int] = {}  # key -> block_id


# ── Routes ──


@router.get("/document/proposal/{proposal_id}/{section_id}", response_model=OnlyOfficeConfigResponse)
async def get_document_config(
    proposal_id: int,
    section_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a document config for OnlyOffice editor.
    Creates a .docx from the section content and returns config to initialize the editor.
    """
    # Fetch the section
    result = await db.execute(
        select(ProposalSection).where(
            ProposalSection.id == section_id,
            ProposalSection.proposal_id == proposal_id,
        )
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Extract text from section content
    text = _section_content_to_text(section.content)
    
    # Create .docx
    docx_bytes = _create_docx_from_text(text, title=section.title)
    
    # Generate unique key
    doc_key = _generate_document_key(proposal_id, section_id)
    
    # Store in memory
    _document_store[doc_key] = docx_bytes
    _key_to_section[doc_key] = (proposal_id, section_id)
    
    # Build URLs
    file_url = f"{settings.backend_public_url}/api/onlyoffice/files/{doc_key}"
    callback_url = f"{settings.backend_public_url}/api/onlyoffice/callback"
    
    logger.info(
        "OnlyOffice document config generated",
        proposal_id=proposal_id,
        section_id=section_id,
        doc_key=doc_key,
        file_url=file_url,
    )
    
    config = _build_config_dict(
        doc_key=doc_key,
        title=f"{section.title}.docx",
        file_url=file_url,
        callback_url=callback_url,
        user_id=str(current_user.id),
        user_name=current_user.name
    )
    
    token = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    
    return OnlyOfficeConfigResponse(
        config=config,
        token=token,
        onlyoffice_url=settings.onlyoffice_url,
    )


@router.get("/document/create", response_model=OnlyOfficeConfigResponse)
async def get_create_document_config(
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Generate a document config for a NEW document (creation flow).
    """
    # Create empty .docx
    docx_bytes = _create_docx_from_text("", title="Nuovo Blocco")
    
    # Generate unique key
    doc_key = _generate_create_document_key()
    
    # Store in memory
    _document_store[doc_key] = docx_bytes
    
    # Build URLs
    file_url = f"{settings.backend_public_url}/api/onlyoffice/files/{doc_key}"
    callback_url = f"{settings.backend_public_url}/api/onlyoffice/callback"
    
    config = _build_config_dict(
        doc_key=doc_key,
        title="Nuovo Documento.docx",
        file_url=file_url,
        callback_url=callback_url,
        user_id=str(current_user.id),
        user_name=current_user.name
    )
    
    token = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    
    return OnlyOfficeConfigResponse(
        config=config,
        token=token,
        onlyoffice_url=settings.onlyoffice_url,
    )


@router.get("/document/library/{block_id}", response_model=OnlyOfficeConfigResponse)
async def get_library_document_config(
    block_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a document config for OnlyOffice editor for a Content Library block.
    """
    # Fetch the block
    result = await db.execute(
        select(ContentBlock).where(ContentBlock.id == block_id)
    )
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    # ContentBlock uses raw strings, but we can treat it similarly
    text = block.content or ""
    
    # Create .docx
    docx_bytes = _create_docx_from_text(text, title=block.title)
    
    # Generate unique key
    doc_key = _generate_library_document_key(block_id)
    
    # Store in memory
    _document_store[doc_key] = docx_bytes
    _key_to_library_block[doc_key] = block_id
    
    # Build URLs
    file_url = f"{settings.backend_public_url}/api/onlyoffice/files/{doc_key}"
    callback_url = f"{settings.backend_public_url}/api/onlyoffice/callback"
    
    logger.info(
        "OnlyOffice document config generated for library block",
        block_id=block_id,
        doc_key=doc_key,
        file_url=file_url,
    )
    
    config = _build_config_dict(
        doc_key=doc_key,
        title=f"{block.title}.docx",
        file_url=file_url,
        callback_url=callback_url,
        user_id=str(current_user.id),
        user_name=current_user.name
    )
    
    token = jwt.encode(config, settings.onlyoffice_jwt_secret, algorithm="HS256")
    
    return OnlyOfficeConfigResponse(
        config=config,
        token=token,
        onlyoffice_url=settings.onlyoffice_url,
    )


@router.get("/files/{doc_key}")
async def serve_document(doc_key: str):
    """Serve a .docx file to OnlyOffice Document Server."""
    docx_bytes = _document_store.get(doc_key)
    if not docx_bytes:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename={doc_key}.docx",
        },
    )


class CallbackPayload(BaseModel):
    key: str
    status: int
    url: str | None = None
    users: list[str] | None = None
    actions: list[dict] | None = None
    changesurl: str | None = None
    history: dict | None = None
    token: str | None = None


@router.api_route("/callback", methods=["GET", "POST"])
async def onlyoffice_callback(
    request: Request,
    payload: CallbackPayload = None,
    db: AsyncSession = Depends(get_db),
):
    """
    OnlyOffice callback endpoint.
    Handles both POST (data) and GET (ping).
    """
    if request.method == "GET":
        return {"error": 0}
    
    if not payload:
         return {"error": 0}

    logger.info("OnlyOffice callback received", key=payload.key, status=payload.status)
    
    # Status 2 = ready to save, 6 = force save
    if payload.status in (2, 6) and payload.url:
        is_library_block = payload.key in _key_to_library_block
        is_section = payload.key in _key_to_section

        if not is_library_block and not is_section:
            logger.warning("Unknown document key in callback", key=payload.key)
            return {"error": 0}
        
        try:
            # Download the updated document from OnlyOffice
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(payload.url)
                response.raise_for_status()
                updated_docx = response.content
            
            # Update in-memory store
            _document_store[payload.key] = updated_docx
            
            # Extract text from the updated .docx
            extracted_text = _extract_text_from_docx(updated_docx)
            
            logger.info(
                "Text extracted from OnlyOffice document",
                key=payload.key,
                text_length=len(extracted_text),
            )
            
            if is_section:
                proposal_id, section_id = _key_to_section[payload.key]
                # Update section content in database
                result = await db.execute(
                    select(ProposalSection).where(
                        ProposalSection.id == section_id,
                        ProposalSection.proposal_id == proposal_id,
                    )
                )
                section = result.scalar_one_or_none()
                if section:
                    section.content = _text_to_tiptap_content(extracted_text)
                    await db.flush()
                    
                    logger.info("Section content updated from OnlyOffice", section_id=section_id)
                
                # Index into RAG
                if extracted_text.strip():
                    try:
                        rag_engine = request.app.state.rag_engine
                        from app.ingestion.pipeline import IngestionPipeline
                        pipeline = IngestionPipeline(rag_engine)
                        
                        stats = await pipeline.ingest_text(
                            text=extracted_text,
                            document_id=section_id,
                            doc_type="proposal_section",
                            metadata={
                                "proposal_id": proposal_id,
                                "section_id": section_id,
                                "source": "onlyoffice",
                            },
                        )
                        
                        logger.info("Section content indexed in RAG", section_id=section_id, stats=stats)
                    except Exception as e:
                        logger.error("Failed to index section in RAG", error=str(e), section_id=section_id)
            
            elif is_library_block:
                block_id = _key_to_library_block[payload.key]
                # Update library block content in database
                result = await db.execute(select(ContentBlock).where(ContentBlock.id == block_id))
                block = result.scalar_one_or_none()
                if block:
                    block.content = extracted_text
                    await db.flush()
                    
                    logger.info("Library block content updated from OnlyOffice", block_id=block_id)
                
                # Index into RAG
                if extracted_text.strip():
                    try:
                        rag_engine = request.app.state.rag_engine
                        from app.ingestion.pipeline import IngestionPipeline
                        pipeline = IngestionPipeline(rag_engine)
                        
                        stats = await pipeline.ingest_text(
                            text=extracted_text,
                            document_id=block_id,
                            doc_type="content_block",
                            metadata={
                                "block_id": block_id,
                                "category": block.category if block else None,
                                "source": "onlyoffice_library",
                            },
                        )
                        
                        logger.info("Library block indexed in RAG", block_id=block_id, stats=stats)
                    except Exception as e:
                        logger.error("Failed to index library block in RAG", error=str(e), block_id=block_id)

        except Exception as e:
            logger.error(
                "Failed to process OnlyOffice callback",
                error=str(e),
                key=payload.key,
            )
    
    # OnlyOffice expects {"error": 0} on success
    return {"error": 0}


@router.post("/forcesave/library/{block_id}")
async def force_save_library(
    block_id: int,
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Trigger a force save in OnlyOffice for a library block.
    """
    # Find the active key for this block
    active_key = None
    for key, bid in _key_to_library_block.items():
        if bid == block_id:
            active_key = key
    
    if not active_key:
        raise HTTPException(status_code=404, detail="No active editing session found")
    
    try:
        command_url = f"{settings.onlyoffice_internal_url}/coauthoring/CommandService.ashx"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                command_url,
                json={
                    "c": "forcesave",
                    "key": active_key,
                },
            )
            result = response.json()
            
        logger.info("Library force save triggered", key=active_key, result=result)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Library force save failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Force save failed: {str(e)}")


@router.post("/forcesave/proposal/{proposal_id}/{section_id}")
async def force_save(
    proposal_id: int,
    section_id: int,
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Trigger a force save in OnlyOffice.
    This calls the OnlyOffice Document Server command service to force saving.
    """
    # Find the active key for this section
    active_key = None
    for key, (pid, sid) in _key_to_section.items():
        if pid == proposal_id and sid == section_id:
            active_key = key
    
    if not active_key:
        raise HTTPException(status_code=404, detail="No active editing session found")
    
    try:
        command_url = f"{settings.onlyoffice_internal_url}/coauthoring/CommandService.ashx"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                command_url,
                json={
                    "c": "forcesave",
                    "key": active_key,
                },
            )
            result = response.json()
            
        logger.info("Force save triggered", key=active_key, result=result)
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Force save failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Force save failed: {str(e)}")


