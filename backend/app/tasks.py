"""
TenderWriter — Celery Tasks

Background tasks for long-running operations.
"""

import asyncio
import io
import logging
from html import escape
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.celery import celery_app
from app.db.database import async_session_factory

logger = logging.getLogger(__name__)


def _extract_text_from_structured_content(content: object) -> str:
    """Flatten TipTap-like content into plain text for safe PDF rendering."""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return ""
    if isinstance(content.get("text"), str):
        return content["text"]
    paragraphs: list[str] = []
    for node in content.get("content") or []:
        if not isinstance(node, dict):
            continue
        text_parts: list[str] = []
        for child in node.get("content") or []:
            if isinstance(child, dict) and isinstance(child.get("text"), str):
                text_parts.append(child["text"])
        joined = "".join(text_parts).strip()
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def _content_to_safe_pdf_html(content: object) -> str:
    text = _extract_text_from_structured_content(content)
    if not text.strip():
        return "<p></p>"
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    return "".join(f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs)


def get_async_session():
    """Reuse the shared async session factory for Celery tasks."""
    return async_session_factory


@celery_app.task(bind=True, max_retries=3)
def index_document_task(self, document_id: int):
    """
    Index a document into the RAG pipeline.
    
    Args:
        document_id: ID of the document to index
    """
    try:
        from app.ingestion.pipeline import IngestionPipeline
        
        async def run():
            async_session = get_async_session()
            async with async_session() as session:
                pipeline = IngestionPipeline(session)
                await pipeline.process_document(document_id)
        
        asyncio.run(run())
        logger.info("Document indexed successfully", document_id=document_id)
        return {"status": "completed", "document_id": document_id}
    
    except Exception as e:
        logger.error("Document indexing failed", document_id=document_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=2)
def generate_proposal_section_task(self, proposal_id: int, section_id: int, prompt: str = None):
    """
    Generate a proposal section using LLM.
    
    Args:
        proposal_id: ID of the proposal
        section_id: ID of the section to generate
        prompt: Optional custom prompt
    """
    try:
        from app.rag.engine import HybridRAGEngine, QueryMode, RAGQuery
        
        async def run():
            engine = HybridRAGEngine()
            await engine.initialize()

            try:
                query_text = prompt or f"Generate content for proposal section {section_id}"
                rag_query = RAGQuery(
                    text=query_text,
                    mode=QueryMode.WRITE_SECTION,
                    section_title=f"Proposal Section {section_id}",
                    instructions=query_text,
                    filters={
                        "proposal_id": proposal_id,
                        "section_id": section_id,
                    },
                )

                return await engine.query(rag_query)
            finally:
                await engine.shutdown()
        
        result = asyncio.run(run())
        
        logger.info("Section generated successfully", proposal_id=proposal_id, section_id=section_id)
        return {
            "status": "completed",
            "proposal_id": proposal_id,
            "section_id": section_id,
            "content": result.answer[:500] if result else None
        }
    
    except Exception as e:
        logger.error("Section generation failed", proposal_id=proposal_id, section_id=section_id, error=str(e))
        raise self.retry(exc=e, countdown=120)


@celery_app.task(bind=True, max_retries=2)
def export_proposal_pdf_task(self, proposal_id: int):
    """
    Export a proposal to PDF.
    
    Args:
        proposal_id: ID of the proposal to export
    """
    try:
        from weasyprint import HTML
        from jinja2 import Template
        
        async def run():
            async_session = get_async_session()
            async with async_session() as session:
                from app.models import Proposal, ProposalSection
                
                result = await session.execute(
                    select(Proposal).where(Proposal.id == proposal_id)
                )
                proposal = result.scalar_one_or_none()
                
                if not proposal:
                    raise ValueError(f"Proposal {proposal_id} not found")
                
                result = await session.execute(
                    select(ProposalSection)
                    .where(ProposalSection.proposal_id == proposal_id)
                    .order_by(ProposalSection.order)
                )
                sections = result.scalars().all()
                
                template_str = """
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>{{ proposal.title }}</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 40px; }
                        h1 { color: #2563eb; }
                        h2 { color: #1e40af; border-bottom: 1px solid #ccc; }
                        .section { margin-bottom: 20px; }
                        .meta { color: #666; font-size: 0.9em; }
                    </style>
                </head>
                <body>
                    <h1>{{ proposal.title }}</h1>
                    <p class="meta">Client: {{ proposal.client or 'N/A' }}</p>
                    {% for section in sections %}
                    <div class="section">
                        <h2>{{ section.title }}</h2>
                        {{ section.safe_html|safe }}
                    </div>
                    {% endfor %}
                </body>
                </html>
                """
                
                template = Template(template_str)
                rendered_sections = [
                    {
                        "title": section.title,
                        "safe_html": _content_to_safe_pdf_html(section.content),
                    }
                    for section in sections
                ]
                html_content = template.render(proposal=proposal, sections=rendered_sections)
                
                pdf_bytes = HTML(string=html_content).write_pdf()
                return pdf_bytes
        
        pdf_bytes = asyncio.run(run())
        
        logger.info("PDF exported successfully", proposal_id=proposal_id)
        return {
            "status": "completed",
            "proposal_id": proposal_id,
            "pdf_size": len(pdf_bytes)
        }
    
    except Exception as e:
        logger.error("PDF export failed", proposal_id=proposal_id, error=str(e))
        raise self.retry(exc=e, countdown=60)


@celery_app.task
def cleanup_old_documents():
    """
    Periodic task to clean up old OnlyOffice documents from MinIO.
    
    Removes documents older than 24 hours.
    """
    from app.api.onlyoffice import _document_store
    
    async def run():
        deleted = await _document_store.cleanup_old_documents(max_age_hours=24)
        return {"status": "completed", "deleted_count": deleted}
    
    result = asyncio.run(run())
    logger.info("Old documents cleanup completed", deleted_count=result["deleted_count"])
    return result


@celery_app.task
def cleanup_expired_otp():
    """
    Periodic task to clean up expired OTP tokens.
    """
    async def run():
        async_session = get_async_session()
        async with async_session() as session:
            from app.models import OTPToken
            
            result = await session.execute(
                delete(OTPToken).where(OTPToken.expires_at < datetime.now(timezone.utc))
            )
            await session.commit()
            
            deleted = result.rowcount
            return {"status": "completed", "deleted_count": deleted}
    
    result = asyncio.run(run())
    logger.info("Expired OTP cleanup completed", deleted_count=result["deleted_count"])
    return result


@celery_app.task
def health_check():
    """Simple health check task."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
