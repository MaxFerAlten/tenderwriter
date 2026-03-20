# KPI Contract V1

This document closes the open Sprint 14 decisions for the TenderWriter KPI reason engine and is the canonical contract for deterministic analytics until the semantic shadow pipeline replaces specific KPIs.

## Decisions Closed

1. Internal score scale is `0-100`.
2. External human-readable scale remains `1-10` for managerial reading and prompt design.
3. Quality index `Q` is calculated as `0.30*A1 + 0.15*A2 + 0.30*A3 + 0.25*A4`.
4. Operational index `E` is calculated as `0.30*B1 + 0.30*B2 + 0.15*B3 + 0.25*B4`.
5. Markov MVP scope is `S4, S5, S6, S8, S9, S10, S11, S12, S13`, with the first reliable empirical calibration focused on `S4, S5, S6, S8, S9`.
6. Semantic scoring priority is `A1`, `A4`, then `A2`, `A3`.

## Health Rules

The state health is intentionally hybrid so it stays faithful to the current TenderWriter admin experience while adopting the new contract metadata.

- `Green`: `Q >= 75`, `E >= 70`, `A4 >= 70`, with no individual KPI in red and no failed compliance gate.
- `Amber`: not green, with recoverable KPI pressure but without explicit red blockers.
- `Red`: any failed compliance gate, or any individual KPI already in red severity inside the snapshot.

## Canonical Score Payload

Each KPI score must expose these fields:

- `kpi_code`
- `score`
- `value`
- `health`
- `severity`
- `source_type`
- `provenance`
- `confidence`
- `evidences`
- `evidence`
- `criticalities`
- `recommendations`
- `recommendation`
- `formula_version`
- `model_version`
- `prompt_version`

`score`, `evidences`, `recommendations` and `source_type` are the canonical fields. `value`, `evidence`, `recommendation` and `provenance` stay available as compatibility aliases for existing consumers.

## Metadata Contract

Each analytical snapshot must expose at least:

- `contract_version = kpi-contract-v1`
- `health_rule_version = tender-health-v1`
- `score_scale_internal = 0-100`
- `score_scale_external = 1-10`
- `formula_bundle_version`
- `model_bundle_version`
- `prompt_bundle_version`
- `markov_phase_scope`
- `markov_reliable_phase_scope`
- `semantic_priority`

## Provenance Contract

- `observed`: directly backed by persisted workflow telemetry.
- `inferred`: derived from mirrored state, structure or fallback heuristics.
- `reconstructed`: produced by history replay/backfill.
- `unknown`: insufficient evidence.

Legacy `measured` values normalize to `observed`.
