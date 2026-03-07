"""
TenderWriter — Celery Tasks

Background tasks for long-running operations.
"""

import asyncio
import io
import logging
from datetime import datetime, timedelta

from celery import Celery
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.celery import celery_app

logger = logging.getLogger(__name__)


def get_async_session():
    """Create async database session for tasks."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session


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
        from app.rag.engine import HybridRAGEngine, QueryMode
        
        async def run():
            engine = HybridRAGEngine()
            await engine.initialize()
            
            query_text = prompt or f"Generate content for proposal section {section_id}"
            
            result = await engine.generate(
                query=query_text,
                mode=QueryMode.WRITE_SECTION,
                proposal_id=proposal_id,
                section_id=section_id,
            )
            
            await engine.shutdown()
            return result
        
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
                        <p>{{ section.content|safe }}</p>
                    </div>
                    {% endfor %}
                </body>
                </html>
                """
                
                template = Template(template_str)
                html_content = template.render(proposal=proposal, sections=sections)
                
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
                delete(OTPToken).where(OTPToken.expires_at < datetime.utcnow())
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
        "timestamp": datetime.utcnow().isoformat()
    }
