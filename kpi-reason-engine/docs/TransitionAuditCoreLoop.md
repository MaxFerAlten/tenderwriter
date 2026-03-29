# Transition Audit Core Loop

This audit captures the current empirical state of the TenderWriter KPI reason engine after the lifecycle corridor hardening that followed Sprint 18.

## Reliable Observed Core Loop

The reason engine has strong observed telemetry for these states and transitions:

- `S0 -> S1` via `tender_document_ingested`
- `S1 -> S2` via `go_decision_recorded`
- `S1 -> S13` via `no_bid_decision_recorded`
- `S2 -> S3` via `contribution_request_wave_opened`
- `S3 -> S4` via `contribution_received`
- `S4 -> S5` via `contribution_review_started` and `review_cycle_started`
- `S4 -> S6` via `coordination_risk_raised`
- `S5 -> S6` via `rework_requested`
- `S6 -> S4` via `rework_reescalated_to_coordination`
- `S6 -> S5` via `rework_resolved`
- `S5 -> S7` via `draft_integrated_ready`
- `S7 -> S8` via `compliance_gate_opened`
- `S8 -> S8` via `compliance_gate_failed`
- `S8 -> S7` via `compliance_gate_passed`
- `S8 -> S6` via `compliance_gate_rework_requested`
- `S8 -> S13` via `tender_stopped_at_gate`
- `S8 -> S9` via `tender_submitted`
- `S9 -> S10` via `clarification_requested`
- `S10 -> S9` via `clarification_closed`
- `S10 -> S11` via `award_confirmed`
- `S10 -> S12` via `loss_reason_recorded`
- `S10 -> S13` via `tender_excluded`, `tender_withdrawn` and `tender_stopped`

## Inferred Fallbacks

When explicit events are missing, the engine still surfaces inferred transitions for:

- `S4 -> S5` from proposal section review state
- `S5 -> S6` from open blocking rework state
- `S7 -> S8` from open gate pressure
- `S9 -> S10` from mirrored clarification pressure
- `S9/S10 -> S13` from mirrored terminal metadata when a terminal event was not preserved in history

## Gaps Still Open

The following areas are still not first-class empirical transitions and remain backlog candidates:

- repeated `S3 -> S4` execution entry still depends on `contribution_received`; section-only execution can still fall back to inferred signals
- generic `tender_stopped` remains context-sensitive and should be preferred only for non-gate terminal closure
- historical tenders synchronized before these events were introduced still need history backfill to cleanly populate the Markov dataset

## Operational Meaning

- `observed` transitions are safe inputs for Markov MVP calibration.
- `inferred` transitions are useful for diagnostics and admin explanation, but should not be treated as equal to empirical counts.
- `reconstructed` snapshots are valid for history replay, not for claiming native event coverage.

## Delivery Implication

The corridor is now explicit enough for Markov calibration on the full lifecycle, but historical tenders should be backfilled after rollout so the newly canonical branches contribute clean empirical counts.
