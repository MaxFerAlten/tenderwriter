# Transition Audit Core Loop

This audit captures the current empirical state of the TenderWriter KPI reason engine after Sprint 14 contract alignment.

## Reliable Observed Core Loop

The reason engine has strong observed telemetry for these states and transitions:

- `S4 -> S5` via `contribution_review_started` and `review_cycle_started`
- `S5 -> S6` via `rework_requested`
- `S6 -> S5` via `rework_resolved`
- `S7 -> S8` via `compliance_gate_opened`
- `S8 -> S8` via `compliance_gate_failed`
- `S8 -> S7` via `compliance_gate_passed`
- `S8 -> S9` via `tender_submitted`
- `S9 -> S10` via `clarification_requested`

## Inferred Fallbacks

When explicit events are missing, the engine still surfaces inferred transitions for:

- `S4 -> S5` from proposal section review state
- `S5 -> S6` from open blocking rework state
- `S7 -> S8` from open gate pressure
- `S9 -> S10` from mirrored clarification pressure

## Gaps Still Open

The following areas are still not first-class empirical transitions and remain backlog candidates:

- `S1` Go / No-Go decisions
- `S2` formal bid planning approval
- explicit `S7` draft integrated ready event
- terminal distinction inside `S13` between `excluded`, `withdrawn` and `no_bid`
- full post-submission closure path from `S10` to `S11`, `S12`, `S13`

## Operational Meaning

- `observed` transitions are safe inputs for Markov MVP calibration.
- `inferred` transitions are useful for diagnostics and admin explanation, but should not be treated as equal to empirical counts.
- `reconstructed` snapshots are valid for history replay, not for claiming native event coverage.

## Delivery Implication

Sprint 14 closes the contract, provenance and audit layer. Sprint 15 and later can now add semantic scoring and Markov calibration on a stable base instead of changing the meaning of the engine while data quality is still moving.
