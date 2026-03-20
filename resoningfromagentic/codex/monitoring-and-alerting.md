# Monitoring And Alerting

## Runtime Endpoints
- `GET /health`: liveness, version, release channel, rollout policy, schema version, output schema versions.
- `GET /ready`: readiness con worker state, queue depth, failed jobs, latest snapshot e dependency breakdown.
- `GET /version-manifest`: manifest completo di contract, output schema, semantic bundle, forecast bundle e versioni persistite nello store.
- `GET /metrics`: snapshot JSON di HTTP traffic, domain events, job runtime, persistence, snapshot governance e version governance.
- `GET /metrics/prometheus`: export testuale Prometheus-style dei segnali principali del servizio.
- `GET /api/admin/kpi/service/status`: vista BFF aggregata per admin e troubleshooting operativo.

## Dashboard Panels
- Request volume e status code da `/metrics.http.breakdown`.
- Average e max latency per route da `/metrics.http.latency_ms`.
- Analysis jobs per status da `/metrics.analysis_jobs.runtime.by_status`.
- Snapshot governance da `/metrics.snapshots`.
- Persisted entities da `/metrics.persistence`.
- Domain event ingestion totals da `/metrics.domain_events.ingested_total`.
- Output schema and contract drift da `/metrics.version_governance` e `/version-manifest`.
- Admin service status via `/api/admin/kpi/service/status` per troubleshooting rapido dal backend.

## Alert Suggestions
- Trigger alert se `ready = false` su `/ready`.
- Trigger alert se `queue_depth > 5` su `/ready` per piu di 10 minuti.
- Trigger alert se `failed_jobs > 0` su `/ready`.
- Trigger alert se `snapshots.latest_generated_at` e piu vecchio di `21600` secondi con `mirrored_tenders > 0`.
- Trigger alert se `/metrics.http.breakdown` mostra `5xx` ripetuti su `/v1/tenders/*/analysis-jobs` o `/v1/tenders/*/forecast`.
- Trigger alert se `persisted_domain_events` cresce ma `persisted_snapshots` resta piatto.
- Trigger alert se `version_governance.snapshot_output_schema_versions` contiene piu di una versione attiva inattesa.
- Trigger alert se il BFF `/api/admin/kpi/service/status` torna `degraded = true`.

## Escalation Path
1. Verificare `/ready` per capire se il problema e `worker`, `snapshot_pipeline` o `schema`.
2. Verificare `/metrics` e `/metrics/prometheus` per quantificare queue, failures e drift di persistence.
3. Verificare `/version-manifest` se il problema riguarda incoerenze di bundle o output schema.
4. Verificare il ledger `kpi_admin_audit_logs` se il problema e nato da mutation admin sensibili.

## Golden Dataset Gate
Prima di ogni release finale, eseguire:
- `test_golden_dataset.py`
- `test_runtime_metrics.py`
- `test_api.py`

Confermare che restino verdi almeno questi casi golden:
- `healthy_submission_path`
- `rework_pressure`
- `compliance_risk`
- `excluded_no_bid`
