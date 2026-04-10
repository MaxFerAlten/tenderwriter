# Refactoring del Flusso Upload PDF Tender — Piano di Implementazione

## Decisioni utente approvate

| Domanda | Decisione |
|---------|-----------|
| `DRAFT → ACTIVE` automatico | **Step esplicito "Attiva tender"** — rimosso dall'upload e dal task |
| Notifiche frontend | **WebSocket/SSE push** per stato ingestione |
| Scope P1/P2 | **Inclusi** — BM25 batch rebuild, OnlyOffice alignment, requirement validation |
| Test | **Ogni modifica certificata con test puntuali** |

---

## Proposed Changes (aggiornato)

### Fase 1 — Modello `Document` + Migration

- [MODIFY] `backend/app/models/__init__.py` — estendere `Document` con `tender_id`, `storage_*`, `source_kind`, `ingestion_*`; aggiungere `Tender.documents`
- [NEW] `backend/migrations/versions/20260410_0009_document_tender_link.py` — Alembic migration
- [NEW] `backend/tests/test_document_model.py` — test unitari modello

### Fase 2 — Upload `202 Accepted` + job Celery

- [MODIFY] `backend/app/api/tenders.py` — endpoint import → crea Document PENDING, upload MinIO, enqueue task, ritorna 202
- [NEW] endpoint `GET /{tender_id}/documents` e `GET /{tender_id}/documents/{document_id}`
- [NEW] `backend/tests/test_tender_import_async.py` — test endpoint refactorato

### Fase 3 — Task Celery orchestratore + SSE push

- [MODIFY] `backend/app/tasks.py` — `index_document_task` diventa orchestratore completo
- [MODIFY] `backend/app/ingestion/pipeline.py` — `process_document()` wrapper, metadata coerenti
- [NEW] SSE endpoint o WebSocket per push stato ingestione
- [NEW] `backend/tests/test_index_document_task.py` — test task con mock pipeline

### Fase 4 — Frontend async upload + notifiche

- [MODIFY] `frontend/src/api/client.ts` — nuova response, polling + SSE listener
- [MODIFY] `frontend/src/pages/Dashboard.tsx` — stato progressivo upload
- [NEW] `frontend/src/api/client.test.ts` — test aggiuntivi

### Fase 5 — P1/P2: BM25, OnlyOffice, step "Attiva tender"

- [MODIFY] `backend/app/rag/sparse_retriever.py` — BM25 batch rebuild
- [MODIFY] `backend/app/api/onlyoffice.py` — allineamento modello documentale
- [NEW] endpoint `POST /{tender_id}/activate` — step esplicito DRAFT → ACTIVE
- [NEW] test per ogni modifica P1/P2
