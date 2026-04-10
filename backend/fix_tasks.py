import sys
import re

file_path = r'D:\tender\tenderwriter\backend\app\tasks.py'
with open(file_path, 'r', encoding='utf-8') as f:
    text = f.read()

new_func = """@celery_app.task(bind=True, max_retries=3)
def index_document_task(self, document_id: int):
    \"\"\"
    Process a document asynchronously: download from MinIO, parse, extract, index,
    stage requirements, update DB status, and send SSE updates.
    \"\"\"
    import tempfile
    import os
    import asyncio
    from minio import Minio
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select, func
    from app.models import Document, IngestionStatus, Tender
    from app.config import settings
    from app.rag.engine import HybridRAGEngine
    from app.ingestion.pipeline import IngestionPipeline
    from app.services.requirement_candidates import stage_extracted_requirement_candidates
    from app.services.tender_requirements import apply_extracted_requirement_candidates, sync_tender_requirements_to_graph
    from app.services.compliance_observability import sync_requirement_compliance_and_gate
    from app.services.kpi_reason_engine import (
        build_tender_document_ingested_event_payload,
        build_requirements_extracted_event_payload,
        sync_tender_and_publish_event,
        publish_domain_event,
    )

    async def run():
        async_session = get_async_session()
        async with async_session() as db:
            # 1. Fetch Document and mark as PROCESSING
            result = await db.execute(
                select(Document).options(selectinload(Document.tender)).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()
            if not doc:
                logger.error("Document not found for processing", document_id=document_id)
                return

            doc.ingestion_status = IngestionStatus.PROCESSING
            doc.ingestion_started_at = func.now()
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

                # 3. Process with IngestionPipeline
                engine = HybridRAGEngine()
                await engine.initialize()
                pipeline = IngestionPipeline(engine)
                
                stats = await pipeline.ingest_file(
                    file_path=tmp_path,
                    document_id=doc.id,
                    doc_type=doc.doc_type,
                    metadata={"original_filename": doc.filename, "tender_id": doc.tender_id}
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
                        extraction_method=str(stats.get("requirement_extraction_method") or "heuristic_v1"),
                        candidates=requirement_candidates,
                        metadata={
                            "content_type": doc.mime_type,
                            "requirements_detected": stats.get("requirements_detected"),
                            "sections_detected": stats.get("sections_detected"),
                            "ingestion_status": stats.get("status"),
                            "requirement_scope": stats.get("requirement_scope"),
                            "requirement_extractor_pipeline": stats.get("requirement_extractor_pipeline"),
                        },
                    )

                    # For now, automatically apply candidates (as the old logic did)
                    created_requirements = apply_extracted_requirement_candidates(tender, requirement_candidates)
                    await db.flush()
                    
                    # Sync to Neo4j
                    graph_synced = await sync_tender_requirements_to_graph(
                        engine,
                        tender,
                        list(tender.requirements or created_requirements),
                    )
                    stats["graph_synced"] = graph_synced
                    
                    # Compute compliance
                    compliance_events = await sync_requirement_compliance_and_gate(
                        db,
                        tender_id=tender.id,
                        actor_id=doc.uploaded_by,
                    )

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

                # 5. Mark Document completed
                doc.ingestion_status = IngestionStatus.COMPLETED
                doc.ingestion_completed_at = func.now()
                doc.chunk_count = stats.get("chunks", 0)
                await db.commit()
                logger.info("Document indexed successfully", document_id=document_id)

            except Exception as inner_e:
                doc.ingestion_status = IngestionStatus.FAILED
                doc.error_message = str(inner_e)
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
        logger.error("Document indexing failed", document_id=document_id, error=str(e))
        raise self.retry(exc=e, countdown=60)
"""

pattern = re.compile(
    r'@celery_app\.task\(bind=True, max_retries=3\)\ndef index_document_task\(self, document_id: int\):.*?(?=@celery_app\.task)', 
    re.DOTALL
)

new_text = pattern.sub(new_func + '\n\n', text)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Done")
