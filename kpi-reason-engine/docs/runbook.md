# KPI Reason Engine Runbook

## Scope
This runbook covers `tw-kpi-reason-engine` release, rollback, replay, and first-level troubleshooting.

## Health And Metrics
- `GET /health`: basic liveness and version.
- `GET /metrics`: runtime counters, latency, persisted gauges, and analysis-job breakdown.
- Primary runtime signals:
  - `http.total_requests`
  - `analysis_jobs.runtime.analysis_jobs.by_status`
  - `persistence.persisted_snapshots`
  - `persistence.persisted_phase_transitions`
  - `domain_events.ingested_total`

## Deploy
1. Apply the service image/build.
2. Run Alembic migrations on startup.
3. Verify `GET /health` returns `healthy`.
4. Verify `GET /metrics` exposes non-empty service metadata.
5. Trigger one manual recompute from admin and confirm a `succeeded` analysis job.

## Rollback
1. Stop new admin-triggered recomputes.
2. Roll back the deployed image to the last known-good version.
3. Re-run the smoke checks on `/health`, `/metrics`, and one tender snapshot.
4. If the schema is forward-only, keep the migrated DB and validate read compatibility before reopening admin actions.

## Replay / Backfill
1. Select the tender from `Observability KPI`.
2. Run `Replay History` from the admin page.
3. Wait for the latest analysis job to complete.
4. Verify the `Persisted history` panel contains reconstructed entries.
5. Verify the latest live snapshot is still the current one after replay.

## Common Incidents
### KPI service unavailable from backend
- Symptom: admin page shows degraded payloads and `service_unavailable` forecast.
- Checks:
  - verify `KPI_REASON_ENGINE_BASE_URL`
  - verify service token mismatch
  - inspect `/metrics` request counts and service logs

### Analysis jobs stuck queued
- Symptom: latest job remains `queued`.
- Checks:
  - worker thread started on service boot
  - runtime metrics show queued jobs growing and no succeeded jobs
  - inspect DB path permissions and recent job error logs

### Unexpected forecast drift
- Symptom: forecast top scenario changes unexpectedly.
- Checks:
  - run golden dataset regression suite
  - compare `analysis_metadata` versions
  - inspect recent domain events and reconstructed history markers
