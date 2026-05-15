"""
TenderWriter — Celery Tasks

Background tasks for long-running operations.
"""

import asyncio
import logging
from datetime import datetime, timezone
from html import escape

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.celery import celery_app
from app.config import settings
from app.ingestion.observability import (
    extract_ingestion_observability,
    update_ingestion_observability,
)

logger = logging.getLogger(__name__)


def _update_document_ingestion_stage(
    doc,
    *,
    stage: str,
    status: str,
    detail: str | None = None,
    stats: dict | None = None,
    error_message: str | None = None,
) -> dict:
    doc.metadata_json = update_ingestion_observability(
        doc.metadata_json,
        stage=stage,
        status=status,
        detail=detail,
        stats=stats,
        error_message=error_message,
    )
    observability = extract_ingestion_observability(doc.metadata_json)
    progress = observability.get("progress")
    if isinstance(progress, (int, float)):
        doc.ingestion_progress = float(progress)
    return observability


def _build_stage_error_message(stage: str, error: object) -> str:
    compact_stage = stage.replace("_", " ")
    return f"[{compact_stage}] {error}"


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
    return "".join(
        f"<p>{escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs
    )


def get_async_session():
    """Create a fresh async engine + session factory for Celery tasks.

    The module-level async_session_factory is bound to the FastAPI event loop.
    Inside a Celery worker, asyncio.run() creates a new loop, causing
    MissingGreenlet / 'attached to a different loop' errors.
    We create an isolated engine per task invocation to avoid this.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    task_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_size=5,
        max_overflow=2,
    )
    return async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(bind=True, max_retries=3)
def index_document_task(self, document_id: int):
    """
    Process a document asynchronously: download from MinIO, parse, extract, index,
    stage requirements, update DB status, and send SSE updates.
    """
    import asyncio
    import os
    import tempfile

    from minio import Minio
    from sqlalchemy import func, select
    from sqlalchemy.orm import selectinload

    from app.config import settings
    from app.ingestion.pipeline import IngestionPipeline
    from app.models import Document, IngestionStatus, Tender
    from app.rag.engine import HybridRAGEngine
    from app.services.compliance_observability import sync_requirement_compliance_and_gate
    from app.services.kpi_reason_engine import (
        build_requirements_extracted_event_payload,
        build_tender_document_ingested_event_payload,
        publish_domain_event,
        sync_tender_and_publish_event,
    )
    from app.services.requirement_candidates import stage_extracted_requirement_candidates
    from app.services.tender_requirements import (
        apply_extracted_requirement_candidates,
        sync_tender_requirements_to_graph,
    )

    async def run():
        async_session = get_async_session()
        async with async_session() as db:
            # 1. Fetch Document and mark as PROCESSING
            result = await db.execute(
                select(Document)
                .options(selectinload(Document.tender).selectinload(Tender.requirements))
                .where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error(f"Document not found for processing: document_id={document_id}")
                return

            doc.ingestion_status = IngestionStatus.PROCESSING
            doc.error_message = None
            doc.ingestion_started_at = func.now()
            _update_document_ingestion_stage(
                doc,
                stage="download",
                status="started",
                detail="Preparing secure download from object storage.",
            )
            await db.commit()

            tmp_path = None
            try:
                # 2. Download from MinIO
                minio_client = Minio(
                    settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure,
                )
                _, ext = os.path.splitext(doc.filename)
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                    tmp_path = tmp.name

                logger.info(f"Downloading {doc.storage_object_name} from MinIO to {tmp_path}")
                minio_client.fget_object(doc.storage_bucket, doc.storage_object_name, tmp_path)
                _update_document_ingestion_stage(
                    doc,
                    stage="download",
                    status="completed",
                    detail="Source document downloaded from object storage.",
                    stats={
                        "storage_bucket": doc.storage_bucket,
                        "source_document_ref": doc.storage_object_name,
                    },
                )
                await db.commit()

                # 3. Process with IngestionPipeline
                engine = HybridRAGEngine()
                await engine.initialize()
                pipeline = IngestionPipeline(engine)

                async def persist_pipeline_stage(event: dict) -> None:
                    _update_document_ingestion_stage(
                        doc,
                        stage=str(event.get("stage") or "unknown"),
                        status=str(event.get("status") or "started"),
                        detail=(
                            str(event.get("detail")) if event.get("detail") is not None else None
                        ),
                        stats=event.get("stats") if isinstance(event.get("stats"), dict) else None,
                    )
                    await db.commit()

                stats = await pipeline.ingest_file(
                    file_path=tmp_path,
                    document_id=doc.id,
                    doc_type=doc.doc_type,
                    metadata={
                        "original_filename": doc.filename,
                        "tender_id": doc.tender_id,
                        "source_document_ref": doc.storage_object_name,
                    },
                    progress_callback=persist_pipeline_stage,
                )
                stats.setdefault("warnings", [])

                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    tmp_path = None

                # 4. Tender specific Requirement Extraction + Graph + Rules
                if doc.tender_id:
                    tender = doc.tender
                    requirement_candidates = list(stats.get("requirement_candidates") or [])

                    # Stage candidates for user to review or fallback
                    await stage_extracted_requirement_candidates(
                        db,
                        tender_id=tender.id,
                        actor_id=doc.uploaded_by,
                        source_document_ref=doc.storage_object_name,
                        filename=doc.filename,
                        extraction_method=str(
                            stats.get("requirement_extraction_method") or "heuristic_v1"
                        ),
                        candidates=requirement_candidates,
                        metadata={
                            "content_type": doc.mime_type,
                            "requirements_detected": stats.get("requirements_detected"),
                            "sections_detected": stats.get("sections_detected"),
                            "ingestion_status": stats.get("status"),
                            "requirement_scope": stats.get("requirement_scope"),
                            "requirement_extractor_pipeline": stats.get(
                                "requirement_extractor_pipeline"
                            ),
                        },
                    )

                    # For now, automatically apply candidates (as the old logic did)
                    created_requirements = apply_extracted_requirement_candidates(
                        tender, requirement_candidates
                    )
                    await db.flush()

                    # Sync to Neo4j
                    _update_document_ingestion_stage(
                        doc,
                        stage="sync_neo4j",
                        status="started",
                        detail="Syncing tender requirements into Neo4j.",
                        stats={
                            "requirements_detected": len(requirement_candidates),
                        },
                    )
                    await db.commit()
                    graph_synced = await sync_tender_requirements_to_graph(
                        engine,
                        tender,
                        list(tender.requirements or created_requirements),
                    )
                    stats["graph_synced"] = graph_synced
                    requirements_in_graph = list(tender.requirements or created_requirements)
                    _update_document_ingestion_stage(
                        doc,
                        stage="sync_neo4j",
                        status="completed",
                        detail="Neo4j synchronization completed.",
                        stats={
                            "graph_synced": graph_synced,
                            "requirements_synced": len(requirements_in_graph),
                        },
                    )
                    await db.commit()

                    # Compute compliance
                    _update_document_ingestion_stage(
                        doc,
                        stage="compliance",
                        status="started",
                        detail="Refreshing compliance observability after requirement sync.",
                    )
                    await db.commit()
                    compliance_events = await sync_requirement_compliance_and_gate(
                        db,
                        tender_id=tender.id,
                        actor_id=doc.uploaded_by,
                    )
                    _update_document_ingestion_stage(
                        doc,
                        stage="compliance",
                        status="completed",
                        detail="Compliance observability refreshed.",
                        stats={
                            "events_published": len(compliance_events),
                        },
                    )
                    await db.commit()

                    # Publish Domain Events
                    await sync_tender_and_publish_event(
                        db,
                        tender_id=tender.id,
                        actor_id=doc.uploaded_by,
                        event_type="tender_document_ingested",
                        event_payload=build_tender_document_ingested_event_payload(
                            document_id=doc.storage_object_name,
                            filename=doc.filename,
                            stats=stats,
                        ),
                    )

                    await publish_domain_event(
                        db,
                        tender_id=tender.id,
                        actor_id=doc.uploaded_by,
                        event_type="requirements_extracted",
                        payload=build_requirements_extracted_event_payload(
                            document_id=doc.storage_object_name,
                            filename=doc.filename,
                            extracted_candidates=requirement_candidates,
                            created_requirements=created_requirements,
                        ),
                    )

                    for event_type, payload in compliance_events:
                        await publish_domain_event(
                            db,
                            tender_id=tender.id,
                            actor_id=doc.uploaded_by,
                            event_type=event_type,
                            payload=payload,
                        )
                else:
                    _update_document_ingestion_stage(
                        doc,
                        stage="sync_neo4j",
                        status="skipped",
                        detail="Skipping Neo4j tender sync because the document is not linked to a tender.",
                    )
                    _update_document_ingestion_stage(
                        doc,
                        stage="compliance",
                        status="skipped",
                        detail="Skipping compliance refresh because the document is not linked to a tender.",
                    )
                    await db.commit()

                # 5. Mark Document completed
                doc.ingestion_status = IngestionStatus.COMPLETED
                doc.ingestion_completed_at = func.now()
                doc.chunk_count = stats.get("chunks", 0)
                _update_document_ingestion_stage(
                    doc,
                    stage="completed",
                    status="completed",
                    detail="Document ingestion finished successfully.",
                    stats={
                        "document_id": doc.id,
                        "chunks": stats.get("chunks", 0),
                        "requirements_detected": stats.get("requirements_detected", 0),
                        "sections_detected": stats.get("sections_detected", 0),
                        "graph_synced": stats.get("graph_synced", False),
                    },
                )
                await db.commit()
                logger.info(f"Document indexed successfully: document_id={document_id}")

            except Exception as inner_e:
                failed_stage = str(
                    extract_ingestion_observability(doc.metadata_json).get("current_stage")
                    or "download"
                )
                _update_document_ingestion_stage(
                    doc,
                    stage=failed_stage,
                    status="failed",
                    detail=f"Failure while executing {failed_stage.replace('_', ' ')}.",
                    error_message=str(inner_e),
                )
                doc.ingestion_status = IngestionStatus.FAILED
                doc.error_message = _build_stage_error_message(failed_stage, inner_e)
                doc.ingestion_completed_at = func.now()
                await db.commit()

                # Clean up if failed
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

                raise inner_e

    try:
        asyncio.run(run())
        return {"status": "completed", "document_id": document_id}
    except Exception as e:
        logger.error(f"Document indexing failed: document_id={document_id}, error={e}")
        raise self.retry(exc=e, countdown=60) from e


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

        logger.info(
            "Section generated successfully", proposal_id=proposal_id, section_id=section_id
        )
        return {
            "status": "completed",
            "proposal_id": proposal_id,
            "section_id": section_id,
            "content": result.answer[:500] if result else None,
        }

    except Exception as e:
        logger.error(
            "Section generation failed",
            proposal_id=proposal_id,
            section_id=section_id,
            error=str(e),
        )
        raise self.retry(exc=e, countdown=120) from e


@celery_app.task(bind=True, max_retries=2)
def export_proposal_pdf_task(self, proposal_id: int):
    """
    Export a proposal to PDF.

    Args:
        proposal_id: ID of the proposal to export
    """
    try:
        from jinja2 import Environment, select_autoescape
        from weasyprint import HTML

        async def run():
            async_session = get_async_session()
            async with async_session() as session:
                from app.models import Proposal, ProposalSection

                result = await session.execute(select(Proposal).where(Proposal.id == proposal_id))
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

                template = Environment(
                    autoescape=select_autoescape(default=True, default_for_string=True)
                ).from_string(template_str)
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
        return {"status": "completed", "proposal_id": proposal_id, "pdf_size": len(pdf_bytes)}

    except Exception as e:
        logger.error("PDF export failed", proposal_id=proposal_id, error=str(e))
        raise self.retry(exc=e, countdown=60) from e


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
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@celery_app.task(bind=True, max_retries=0)
def run_rehearsal_task(self, rehearsal_run_id: int):
    """Execute a previously-queued :class:`RehearsalRun`.

    The run row must already exist (created synchronously by
    ``POST /api/intelligence/rehearsals``). This task is the
    asynchronous counterpart: it loads the run, delegates to
    :class:`TenderRehearsalService` and surfaces an operational
    summary in the Celery result payload.

    Operational semantics:

    * ``COMPLETED`` runs are short-circuited at the task layer
      (``status: already_completed``) — never re-executed.
    * ``FAILED`` runs are not retried automatically; an explicit
      caller must request a new run if a rerun is desired.
    * KPI summary sync failures never flip the run to ``failed``.
    * Hard transport/db exceptions propagate (Celery records FAILURE);
      Celery auto-retry is disabled (``max_retries=0``).
    """

    from sqlalchemy import func

    from app.intelligence.rehearsal import TenderRehearsalService
    from app.intelligence.tools import build_default_tool_registry
    from app.models import (
        RehearsalRecommendation,
        RehearsalRecommendationStatus,
        RehearsalRun,
        RehearsalRunStatus,
    )

    async def _execute():
        async_session = get_async_session()
        registry = build_default_tool_registry()
        service = TenderRehearsalService(registry)
        async with async_session() as db:
            initial = await db.get(RehearsalRun, rehearsal_run_id)
            if initial is None:
                return {
                    "status": "not_found",
                    "rehearsal_run_id": rehearsal_run_id,
                }
            already_completed = initial.status == RehearsalRunStatus.COMPLETED

            try:
                run = await service.execute_run(db, run_id=rehearsal_run_id)
            except Exception as exc:
                # Service marks run FAILED in DB; surface a structured
                # payload instead of triggering Celery retry.
                logger.exception(
                    "Rehearsal task failed",
                    extra={"rehearsal_run_id": rehearsal_run_id},
                )
                refreshed = await db.get(RehearsalRun, rehearsal_run_id)
                tender_id = getattr(refreshed, "tender_id", None)
                proposal_id = getattr(refreshed, "proposal_id", None)
                return {
                    "status": "failed",
                    "rehearsal_run_id": rehearsal_run_id,
                    "tender_id": tender_id,
                    "proposal_id": proposal_id,
                    "error": str(exc)[:2000],
                    "failed_stage": "execute_run",
                }

            rec_total = (
                await db.execute(
                    select(func.count())
                    .select_from(RehearsalRecommendation)
                    .where(RehearsalRecommendation.rehearsal_run_id == run.id)
                )
            ).scalar_one()
            rec_blocking = (
                await db.execute(
                    select(func.count())
                    .select_from(RehearsalRecommendation)
                    .where(RehearsalRecommendation.rehearsal_run_id == run.id)
                    .where(RehearsalRecommendation.is_blocking.is_(True))
                    .where(RehearsalRecommendation.status == RehearsalRecommendationStatus.PROPOSED)
                )
            ).scalar_one()

            if already_completed:
                top_status = "already_completed"
            elif run.status == RehearsalRunStatus.COMPLETED:
                top_status = "completed"
            elif run.status == RehearsalRunStatus.FAILED:
                top_status = "failed"
            else:
                top_status = run.status.value if run.status else "unknown"

            return {
                "status": top_status,
                "rehearsal_run_id": run.id,
                "tender_id": run.tender_id,
                "proposal_id": run.proposal_id,
                "overall_score": run.overall_score,
                "health_projection": run.health_projection,
                "persona_divergence": run.persona_divergence,
                "recommendations": int(rec_total or 0),
                "blocking_recommendations": int(rec_blocking or 0),
                "kpi_summary_synced": getattr(run, "kpi_summary_sync_status", None),
            }

    return asyncio.run(_execute())


@celery_app.task(bind=True, max_retries=0)
def run_proposal_writer_task(self, request_payload: dict):
    """Run :class:`ProposalWriterAgent` asynchronously.

    Designed for heavy generations where the synchronous
    ``POST /api/intelligence/proposal-writer/draft`` would exceed the
    request timeout. The Celery payload mirrors the API result.

    ``request_payload`` is the JSON-serialisable form of
    :class:`ProposalWriterRequest`. The task validates the payload via
    Pydantic, builds an agent against the active RAG engine, and
    returns ``ProposalWriterResult.model_dump()``.

    Operational rules:

    * No auto-retry on logic failures (``max_retries=0``).
    * Caller-facing validation errors are surfaced as
      ``{"status": "invalid_request", ...}`` instead of raising.
    * Apply mutations follow the same single-section contract as the
      sync endpoint.
    """

    from app.intelligence.lifecycle_projector import get_active_rag_engine
    from app.intelligence.proposal_writer_agent import (
        ProposalWriterAgent,
        ProposalWriterError,
    )
    from app.intelligence.proposal_writer_models import ProposalWriterRequest
    from app.intelligence.tools import build_default_tool_registry

    try:
        request = ProposalWriterRequest.model_validate(request_payload)
    except Exception as exc:
        logger.warning(
            "proposal_writer_task.invalid_request",
            extra={"error": str(exc)},
        )
        return {"status": "invalid_request", "error": str(exc)}

    async def _execute():
        async_session = get_async_session()
        registry = build_default_tool_registry()
        agent = ProposalWriterAgent(registry=registry, rag_engine=get_active_rag_engine())
        async with async_session() as db:
            try:
                result = await agent.execute(db, request)
            except ProposalWriterError as exc:
                return {
                    "status": "invalid_request",
                    "tender_id": request.tender_id,
                    "proposal_id": request.proposal_id,
                    "section_id": request.section_id,
                    "error": str(exc),
                }
            if request.apply:
                await db.commit()
            return {
                "status": "ok",
                **result.model_dump(),
            }

    return asyncio.run(_execute())
