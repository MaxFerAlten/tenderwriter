# KPI Reason Engine Runbook

## Scope
Questo runbook copre `tw-kpi-reason-engine` per deploy, rollback, replay/backfill, troubleshooting runtime e verifica finale di Sprint 21.

## Runtime Endpoints
- `GET /health`: liveness, versioni base, output schema version e network boundary.
- `GET /ready`: readiness con dependency breakdown (`sqlite_store`, `analysis_job_worker`, `snapshot_pipeline`).
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
3. Verificare `GET /health` con `ready = true` o almeno con schema e versioni coerenti.
4. Verificare `GET /ready` ritorni `200` e `status = ready`.
5. Verificare `GET /version-manifest` e confermare `snapshot-output-v1`, `forecast-output-v1`, `version-manifest-v1`.
6. Verificare `GET /metrics/prometheus` ritorni le serie principali.
7. Verificare dal backend `GET /api/admin/kpi/service/status`.
8. Eseguire una recompute manuale e verificare job `succeeded`.

## Rollback
1. Bloccare nuove mutation admin sensibili (`portfolio/resync`, `recompute`, `history/backfill`).
2. Tornare all’immagine precedente del servizio KPI.
3. Verificare compatibilita read-only del DB e del ledger admin.
4. Eseguire smoke check su `/health`, `/ready`, `/version-manifest` e uno snapshot tender.
5. Riaprire le action admin solo dopo conferma di readiness verde.

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
  - verificare permessi DB e path storage
  - verificare `failed_jobs`

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
