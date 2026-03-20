# Sprint 21 Production Closure

## Outcome
Sprint 21 porta il KPI reason engine da servizio solido a servizio production-grade e governabile.

## Delivered
- Runtime endpoints finali: `health`, `ready`, `version-manifest`, `metrics`, `metrics/prometheus`
- Version governance esplicita per snapshot e forecast output schema
- Readiness reale con soglie su queue, failed jobs e stale snapshot
- Runtime metrics arricchite con snapshot governance e version governance
- BFF admin `service/status`
- Ledger persistente per mutation admin sensibili in `kpi_admin_audit_logs`
- Runbook, monitoring guidance e release checklist aggiornati

## Validation
- KPI engine API suite
- KPI engine runtime metrics suite
- KPI engine golden dataset suite
- Backend KPI client suite
- Backend KPI admin API suite
- Backend route registration suite

## Acceptance
La release Sprint 21 si considera chiusa quando:
- `ready = true` nei smoke test
- `version-manifest` espone versioni coerenti
- nessuna regressione golden resta aperta
- il BFF admin vede stato servizio e audit trail minimo persistente
