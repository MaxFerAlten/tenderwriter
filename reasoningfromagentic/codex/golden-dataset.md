# Golden Dataset

Il golden dataset KPI e la baseline ufficiale di regressione per la release finale del reason engine dopo Sprint 21.

## Cases
- `healthy_submission_path`: atteso `S7`, health green, forecast guidato da `submit_on_time`.
- `rework_pressure`: atteso `S6`, health red, forecast guidato da `extended_rework`.
- `compliance_risk`: atteso `S8`, health red, forecast guidato da `extended_rework`.
- `excluded_no_bid`: atteso `S13`, forecast guidato da `stop_locked`.

## Coverage Intent
Il golden dataset protegge contemporaneamente:
- stabilita di `snapshot`
- stabilita di `forecast`
- stabilita di `transitions`
- coerenza del core lifecycle gia rilasciato
- regressione del Markov full lifecycle rispetto ai casi canonici

## Source Of Truth
- Fixture definitions: [golden_dataset.py](D:/tender/tenderwriter/kpi-reason-engine/tests/golden_dataset.py)
- Regression suite: [test_golden_dataset.py](D:/tender/tenderwriter/kpi-reason-engine/tests/test_golden_dataset.py)
- Runtime suite: [test_runtime_metrics.py](D:/tender/tenderwriter/kpi-reason-engine/tests/test_runtime_metrics.py)
- API suite: [test_api.py](D:/tender/tenderwriter/kpi-reason-engine/tests/test_api.py)

## Release Gate
Una release finale e accettabile solo se:
- il golden dataset resta verde
- le versioni di output schema restano coerenti con `/version-manifest`
- `ready = true` sul servizio durante i smoke test
