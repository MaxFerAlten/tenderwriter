# Release Checklist

## Functional
- [x] Snapshot, diagnostics, transitions, forecast e history replay sono esposti dal KPI engine.
- [x] `tw-backend` proxy admin KPI queries e mutation via BFF.
- [x] Admin UI supporta `Recompute KPI`, `Replay History` e controllo lifecycle.
- [x] Runtime endpoints finali `health`, `ready`, `version-manifest`, `metrics`, `metrics/prometheus` sono disponibili.
- [x] Il backend espone `GET /api/admin/kpi/service/status`.
- [x] Le mutation admin sensibili persistono audit trail in `kpi_admin_audit_logs`.

## Quality Gates
- [x] Golden dataset regression suite passa.
- [x] KPI engine automated tests passano.
- [x] Runtime metrics suite passa.
- [x] Backend KPI tests passano.
- [x] Frontend tests passano.
- [x] Frontend production build passa.

## Operability
- [x] `/health` e `/ready` sono disponibili e coerenti.
- [x] `/version-manifest` espone contract, output schema e versioni persistite.
- [x] `/metrics` e `/metrics/prometheus` sono disponibili.
- [x] Runbook esiste per deploy, rollback, replay e troubleshooting.
- [x] Monitoring and alerting guidance e versionata nel repo.
- [x] Output schema versioning e release governance sono documentati.

## Security And Governance
- [x] Il servizio KPI resta su boundary `internal_only`.
- [x] Le action admin sensibili hanno ledger persistente minimo oltre al log strutturato.
- [x] La readiness segnala queue saturation, failed jobs e stale snapshot.

## Sprint 21 Closure
- [x] Nessun gap residuo accettato per il rilascio finale all’interno del perimetro Sprint 21.
