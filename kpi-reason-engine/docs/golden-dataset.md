# Golden Dataset

The KPI golden dataset is the official regression baseline for Sprint 13 release readiness.

## Cases
- `healthy_submission_path`: expected `S7`, green health, forecast led by `submit_on_time`.
- `rework_pressure`: expected `S6`, red health, forecast led by `extended_rework`.
- `compliance_risk`: expected `S8`, red health, forecast led by `extended_rework`.
- `excluded_no_bid`: expected `S13`, forecast led by `stop_locked`.

## Source Of Truth
- Fixture definitions: [golden_dataset.py](D:/tender/tenderwriter/kpi-reason-engine/tests/golden_dataset.py)
- Regression suite: [test_golden_dataset.py](D:/tender/tenderwriter/kpi-reason-engine/tests/test_golden_dataset.py)
