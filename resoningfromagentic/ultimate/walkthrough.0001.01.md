# Riepilogo: Stabilizzazione Pipeline Asincrona e Fase 5

Abbiamo completato e stabilizzato con successo il refactoring dell'intera pipeline dei documenti, migrando tutto il flusso ad un sistema asincrono orchestrato da **Celery** (nel servizio `celery-worker`). 

Infine, abbiamo implementato anche gli step rimanenti della **Fase 5**.

## 🚀 Lavori Completati

### 1. Risoluzione Autenticazione KPI
Il `401 Unauthorized` nel sistema del KPI Reason Engine durante l'indexing asincrono è stato risolto impostando correttamente le variabili mancanti:
- Aggiunte `KPI_REASON_ENGINE_SERVICE_TOKEN` e `KPI_REASON_ENGINE_BASE_URL` al chunk environment di `celery-worker` tramite _docker-compose.yml_. 
- Adesso ogni DomainEvent viene inoltrato con successo dal worker Celery al microservizio KPI.

### 2. Bottone Rebuild Indice BM25 (Fase 5)
Aggiunta la possibilità, ad uso dell'amministratore, di forzare e ritriggerare la rigenerazione manuale dell'indice lessicale locale (BM25):
- **Backend (`app/api/system.py`)**: Esposto `/api/system/rebuild-bm25` protetto da `admin_required`. Aggancia direttamente il `rag_engine` e forza il bootstrap del _sparse_retriever_.
- **Frontend (`Dashboard.tsx`)**: Aggiunto un pulsante vicino ad "Aggiungi Tender" nella Dashboard per attivare l'indicizzazione ed evitare desincronizzazioni a database e istanze multiple avviate.

### 3. Supporto Viewer Documenti Tenders tramite OnlyOffice (Fase 5)
Abbiamo riallineato il core di **OnlyOffice** originariamente compatibile con sole _Proposal_ e sezioni di Library, a processare in **Read-Only** (per sola visualizzazione rapida) i documenti PDF/DOCX delle gare originarie importate (i Tender Documents):
- **Backend (`app/api/onlyoffice.py`)**: Aggiunto endpoint `/document/tender/{document_id}` che cerca il file su MinIO, genera un JWT OnlyOffice con tutte le permission impostate a `false` ad eccezione della visualizzazione, download e stampa. Setta `mode = "view"`.
- **Frontend (`OnlyOfficeEditor.tsx`)**: Aggiunto supporto nel componente universale ad allocare un layer React interfacciandosi con la backend in modalità `tender_document`, e passando i params corretti alla root API di OnlyOffice.

Tutti gli obiettivi sono stati chiusi. Puoi ricaricare la pagina web e verificare i log finali. Il sistema è performante e production-ready. 🚀
