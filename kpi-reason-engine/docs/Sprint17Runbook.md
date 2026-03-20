# Sprint 17 Runbook

## Scope
Sprint 17 productizes provenance, confidence and rollout governance for the KPI reason engine.

## Rollout policies
- `legacy`: disable semantic shadow and Markov forecast exposure.
- `shadow_only`: keep A1/A4 semantic shadow enabled, force forecast to heuristic mode.
- `markov_only`: keep Markov forecast enabled, disable A1/A4 shadow payloads.
- `full`: enable both semantic shadow and Markov forecast.

## Admin UX signals
- KPI cards show `observed`, `inferred` or `reconstructed` provenance from `source_type`.
- A1 and A4 show `shadow` only when semantic shadow rollout is active.
- Forecast shows `predicted` when heuristic fallback is active.
- Forecast shows `calibrated` when Markov core loop is active.
- Forecast shows `locked` when the tender is already in a terminal phase.

## Runtime checks
Verify these fields on snapshot and forecast payloads:
- `analysis_metadata.rollout_policy`
- `analysis_metadata.shadow_rollout_enabled`
- `analysis_metadata.markov_rollout_enabled`
- `analysis_metadata.forecast_engine_active`
- `analysis_metadata.forecast_signal_type`
- `analysis_metadata.forecast_fallback_reason`

## Regression pack
Run from repository root:
- `D:\tender\tenderwriter\venv\Scripts\python.exe -m unittest discover -s tests -p test_api.py` in `kpi-reason-engine`
- `D:\tender\tenderwriter\venv\Scripts\python.exe -m unittest tests.test_kpi_admin_api` in `backend`
- `Set-Location frontend; npm run test -- --run`
- `Set-Location frontend; npm run build`

## Release sign-off
Release can proceed when:
- KPI engine tests are green.
- Backend admin proxy tests are green.
- Frontend tests and build are green.
- Snapshot exposes rollout metadata coherently.
- Forecast explains whether it is predicted or calibrated.
- A1 and A4 shadow visibility matches the selected rollout policy.
