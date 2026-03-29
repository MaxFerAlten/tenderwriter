# KPI Reason Engine Runbook

## Scope
Questo runbook copre `tw-kpi-reason-engine` per deploy, rollback, replay/backfill, troubleshooting runtime e verifica finale di Sprint 21.

## Current Storage Baseline
- Dal `2026-03-29` il servizio gira in modalita `PostgreSQL-only`.
- Lo store analitico usa `KPI_REASON_ENGINE_DATABASE_URL` con schema dedicato `kpi_engine`.
- Le migrazioni Alembic vengono applicate su startup; lo schema corrente atteso e `20260329_0004`.
- Le colonne strutturate principali sono native PostgreSQL:
  - `jsonb` per payload, metadata, snapshot e descriptor.
  - `timestamp with time zone` per campi temporali operativi e analitici.
- Non esiste piu un volume runtime `./kpi-reason-engine/data:/app/data`.
- `KPI_REASON_ENGINE_LEGACY_DATABASE_PATH` deve restare vuoto a regime.
- `KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP` e `KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION` devono restare `false` a regime.

## Runtime Endpoints
- `GET /health`: liveness, versioni base, output schema version e network boundary.
- `GET /ready`: readiness con dependency breakdown (`sqlite_store`, `analysis_job_worker`, `snapshot_pipeline`).
  Nota: `sqlite_store` e un nome storico del payload di readiness; in produzione il backing store e PostgreSQL.
- `GET /version-manifest`: manifest versionale del servizio e delle versioni persistite nello store.
- `GET /metrics`: metriche JSON per dashboard e debugging.
- `GET /metrics/prometheus`: export Prometheus-style.
- `GET /api/admin/kpi/service/status`: vista admin aggregata lato backend.

## Primary Runtime Signals
- `ready`
- `queue_depth`
- `failed_jobs`
- `latest_snapshot_generated_at`
- `http.total_requests`
- `analysis_jobs.runtime.by_status`
- `snapshots.reconstructed_total`
- `snapshots.semantic_fallback_total`
- `version_governance.snapshot_output_schema_versions`
- `version_governance.model_versions`

## Deploy
1. Applicare la nuova build del servizio KPI.
2. Lasciare eseguire le migration su startup.
3. Verificare che l'ambiente punti a PostgreSQL:
   - `KPI_REASON_ENGINE_DATABASE_URL` valorizzata
   - `KPI_REASON_ENGINE_DATABASE_SCHEMA=kpi_engine`
   - `KPI_REASON_ENGINE_LEGACY_DATABASE_PATH` vuoto
   - nessun mount `/app/data`
4. Verificare `GET /health` con `ready = true` o almeno con schema e versioni coerenti.
5. Verificare `schema_version = 20260329_0004` o successiva compatibile.
6. Verificare `GET /ready` ritorni `200` e `status = ready`.
7. Verificare `GET /version-manifest` e confermare `snapshot-output-v1`, `forecast-output-v1`, `version-manifest-v1`.
8. Verificare `GET /metrics/prometheus` ritorni le serie principali.
9. Verificare dal backend `GET /api/admin/kpi/service/status`.
10. Eseguire una recompute manuale e verificare job `succeeded`.

## Backup And Restore
### Backup
1. Eseguire il backup dal database PostgreSQL, non dal filesystem del container.
2. Esempio:
   - `docker exec tw-postgres pg_dump -U tenderwriter -d tenderwriter -n kpi_engine > kpi_engine.sql`
3. Conservare insieme dump schema e credenziali/parametri dell'ambiente.

### Restore
1. Portare il servizio KPI in manutenzione o fermarlo.
2. Ripristinare lo schema `kpi_engine` nel PostgreSQL target.
3. Riavviare `tw-kpi-reason-engine`.
4. Verificare `/health`, `/ready`, `/version-manifest` e uno snapshot reale.

## Rollback
1. Bloccare nuove mutation admin sensibili (`portfolio/resync`, `recompute`, `history/backfill`).
2. Tornare all’immagine precedente del servizio KPI.
3. Verificare compatibilita read-only del DB e del ledger admin.
4. Verificare che la versione precedente sia compatibile con lo schema PostgreSQL gia migrato.
5. Eseguire smoke check su `/health`, `/ready`, `/version-manifest` e uno snapshot tender.
6. Riaprire le action admin solo dopo conferma di readiness verde.

## Legacy Recovery Only
Usare questa sezione solo per recupero straordinario da un vecchio dump SQLite archiviato.

1. Estrarre il dump SQLite legacy in un path temporaneo esterno al container.
2. Impostare temporaneamente:
   - `KPI_REASON_ENGINE_LEGACY_DATABASE_PATH=<path sqlite>`
   - `KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP=true`
   - `KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION=true`
3. Avviare il servizio una sola volta fino a completamento della migrazione e della validazione conteggi.
4. Ripristinare subito la configurazione di regime:
   - `KPI_REASON_ENGINE_LEGACY_DATABASE_PATH=`
   - `KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP=false`
   - `KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION=false`
5. Riavviare il servizio e verificare che nei log compaiano `legacy_source_path: null`, `migration_report: null`, `validation_report: null`.

## Replay / Backfill
1. Aprire `Observability KPI` e selezionare il tender.
2. Eseguire `Replay History` o `History Backfill`.
3. Attendere il completamento dell’analysis job.
4. Verificare che il pannello `Persisted history` contenga voci `reconstructed`.
5. Verificare che lo snapshot live corrente resti quello finale dopo il replay.
6. Verificare il ledger `kpi_admin_audit_logs` per la mutation sensibile effettuata.

## Common Incidents
### KPI service unavailable from backend
- Sintomo: `degraded = true` su `/api/admin/kpi/service/status`.
- Controlli:
  - verificare `KPI_REASON_ENGINE_BASE_URL`
  - verificare token service
  - verificare `/health` e `/ready`
  - verificare HTTP counts e errori su `/metrics`

### Analysis jobs stuck queued
- Sintomo: `queue_depth` cresce e `worker_running = false` oppure nessun `succeeded`.
- Controlli:
  - verificare `/ready`
  - verificare thread worker attivo
  - verificare permessi DB e connettivita PostgreSQL
  - verificare `failed_jobs`

### PostgreSQL schema mismatch
- Sintomo: `/health` o `/ready` degradati dopo deploy, oppure schema version inattesa.
- Controlli:
  - verificare `KPI_REASON_ENGINE_DATABASE_URL`
  - verificare `KPI_REASON_ENGINE_DATABASE_SCHEMA`
  - verificare i log Alembic su startup
  - verificare `schema_version` da `/health`
  - verificare che il servizio abbia accesso allo schema `kpi_engine`

### Legacy migration unexpectedly triggered
- Sintomo: nei log compaiono `migration_report` o `validation_report` non null in un deploy ordinario.
- Controlli:
  - verificare che `KPI_REASON_ENGINE_LEGACY_DATABASE_PATH` sia vuoto
  - verificare che `KPI_REASON_ENGINE_AUTO_MIGRATE_LEGACY_ON_STARTUP=false`
  - verificare che `KPI_REASON_ENGINE_VALIDATE_LEGACY_MIGRATION=false`
  - verificare che il container non abbia mount `/app/data`

### Snapshot pipeline stale
- Sintomo: `/ready` segnala snapshot stale.
- Controlli:
  - verificare `latest_snapshot_generated_at`
  - verificare crescita di `persisted_domain_events`
  - verificare recompute recente e log del worker

### Version drift
- Sintomo: output schema o bundle inattesi tra snapshot e runtime.
- Controlli:
  - verificare `/version-manifest`
  - verificare `/metrics.version_governance`
  - verificare `kpi_model_versions`

### Admin mutation dispute
- Sintomo: serve ricostruire chi ha rilanciato resync/recompute/backfill.
- Controlli:
  - consultare `kpi_admin_audit_logs`
  - consultare log strutturati `admin_kpi.audit`
