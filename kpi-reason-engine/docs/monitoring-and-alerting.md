# Monitoring And Alerting

## Dashboard Panels
- Request volume by route and status code from `/metrics.http.breakdown`
- Average and max route latency from `/metrics.http.latency_ms`
- Analysis jobs by status from `/metrics.analysis_jobs.runtime.by_status`
- Analysis jobs by type and status from `/metrics.analysis_jobs.runtime.by_type_and_status`
- Persisted entities from `/metrics.persistence`
- Domain event ingestion totals from `/metrics.domain_events.ingested_total`

## Alert Suggestions
- Trigger alert if `analysis_jobs.runtime.analysis_jobs.by_status.failed` increases between two checks.
- Trigger alert if `analysis_jobs.runtime.analysis_jobs.by_status.queued` grows for 10 minutes without a matching increase in `succeeded`.
- Trigger alert if `/metrics.http.breakdown` shows repeated `5xx` on `/v1/tenders/*/analysis-jobs`.
- Trigger alert if `persisted_domain_events` grows but `persisted_snapshots` stays flat.

## Golden Dataset Gate
Before release, run the golden dataset regression suite and confirm every case still matches:
- `healthy_submission_path`
- `rework_pressure`
- `compliance_risk`
- `excluded_no_bid`
