# Release Checklist

## Functional
- [x] Snapshot, diagnostics, transitions, forecast, and history replay are exposed by the KPI engine.
- [x] `tw-backend` proxies admin KPI queries and actions through the BFF.
- [x] Admin UI supports `Recompute KPI` and `Replay History`.

## Quality Gates
- [x] Golden dataset regression suite passes.
- [x] KPI engine automated tests pass.
- [x] Backend KPI tests pass.
- [x] Frontend tests pass.
- [x] Frontend production build passes.

## Operability
- [x] `/health` and `/metrics` are available.
- [x] Runbook exists for deploy, rollback, replay, and troubleshooting.
- [x] Monitoring and alerting guidance is versioned in the repo.

## Readiness Notes
- Forecast is still rule-based, not calibrated on long-term historical data.
- Admin audit trail is currently structured logging, not a dedicated database ledger.
- Metrics are exposed as JSON for integration with the platform monitoring layer.
