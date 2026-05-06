# Asynchronous Tender Document Upload Refactoring

The system has been successfully refactored from a synchronous, blocking "upload-then-parse" flow to an entirely asynchronous, event-driven celery architecture.

## Overview of Changes

### 1. Database Mapping (Phase 1)
- Expanding the `Document` model to natively track lifecycle events via fields like `ingestion_status`, `error_message`, `chunk_count`, and `ingestion_completed_at`.
- Established a robust bidirectional relationship between the `Tender` entity and its `Document`s. 

### 2. API Reponses (Phase 2)
- Re-architected `POST /api/tenders/{tender_id}/import` to instantly return a `202 Accepted` response.
- Introduced explicit tender activation logic through a new `POST /{tender_id}/activate` endpoint, replacing auto-activation inside the upload logic.
- Robust unit tests simulating the MinIO upload and Celery worker environments using mock injection models to verify the asynchronous integration.

### 3. Task Orchestration (Phase 3)
- Implemented `index_document_task` in `tasks.py`, enabling Celery to download user files securely via MinIO object storage.
- Integrated the legacy orchestration tasks (Requirement Extraction heuristics, Knowledge Graph Sync, and Neo4J auditing) entirely into the Celery task loop context.
- Exposed a secure `GET /{tender_id}/documents/{document_id}/stream` (Server-Sent Events) endpoint, actively broadcasting parsing progress updates and LLM requirement fallback events directly to connected clients.

### 4. Client Resiliency (Phase 4)
- Added continuous real-time React logic inside `Dashboard.tsx` establishing unidirectional real-time data flow with `EventSource`.
- Patched Typescript contracts inside `client.ts` predicting the delayed task outcomes from the new async backend. 
- Designed a distinct progressively updating `TenderCard` rendering realtime state tracking (`Uploading...` => `Parsing...` => `Activate`).

## Next Steps

With the entire infrastructure functioning on asynchronous queues, you are now prepared to explore remaining P1/P2 lifecycle operations like batch rebuilding BM25 indexes or aligning OnlyOffice capabilities under an event-driven domain umbrella.
