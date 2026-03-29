# Canonical Event Catalog

This document freezes the canonical lifecycle events used by `tw-kpi-reason-engine` after Sprint 18.

## Event Envelope

Every event sent to the KPI engine must provide:

- `event_type`: stable domain identifier.
- `external_tender_id`: cross-service tender id.
- `occurred_at`: UTC business timestamp.
- `actor_id`: optional actor that triggered the event.
- `source`: emitting subsystem such as `tw-backend` or `admin-ui`.
- `schema_version`: payload schema version.
- `payload`: event-specific data.

## Canonical Lifecycle Corridor

The lifecycle is intentionally split across preparation, execution, submission reliability and terminal closure.

### Intake and early governance

#### `tender_created`
Minimum payload:
- `title`
- `customer_name`
- `due_at`

#### `tender_document_ingested`
Minimum payload:
- `document_id`
- `document_type`
- `filename`

#### `requirements_extracted`
Minimum payload:
- `requirement_count`
- `extractor_version`

#### `go_decision_recorded`
Moves the tender into formal bid planning.
Minimum payload:
- `decision`
- `decided_at`
- `reason_code`
- `notes`

#### `no_bid_decision_recorded`
Closes the tender as an explicit no-bid decision.
This is the only canonical no-bid closure event and it must not be emitted from terminal outcome controls.
Minimum payload:
- `decision`
- `decided_at`
- `reason_code`
- `notes`

### Planning and contribution orchestration

#### `bid_plan_created`
Minimum payload:
- `plan_status`
- `planned_at`
- `milestone_count`
- `owner_user_ids`

#### `bid_plan_approved`
Minimum payload:
- `plan_status`
- `planned_at`
- `owner_user_ids`

#### `bid_team_assigned`
Minimum payload:
- `owner_user_ids`
- `planned_at`

#### `contribution_request_wave_opened`
Minimum payload:
- `opened_at`
- `contribution_count`
- `department_count`
- `notes`

#### `contribution_assignment_confirmed`
Minimum payload:
- `external_contribution_id`
- `requested_to_label`
- `request_channel`
- `due_at`

### Proposal execution core loop

#### `proposal_created`
Minimum payload:
- `proposal_id`
- `section_count`

#### `proposal_section_updated`
Minimum payload:
- `external_section_id`
- `change_type`
- `status`

#### `contribution_request_created`
Minimum payload:
- `contribution_unit_id`
- `department_id`
- `due_at`

#### `contribution_due_date_set`
Minimum payload:
- `contribution_unit_id`
- `due_at`

#### `contribution_received`
Minimum payload:
- `contribution_unit_id`
- `received_at`
- `delivery_type`

#### `coordination_risk_raised`
Explicitly pushes the tender from execution back into blocking coordination/rework.
Minimum payload:
- `external_rework_id`
- `external_contribution_id`
- `requested_at`
- `reason_code`
- `notes`

#### `rework_reescalated_to_coordination`
Closes the blocking rework state and returns the tender to coordination before a new review cycle.
Minimum payload:
- `external_rework_id`
- `external_contribution_id`
- `resolved_at`
- `reason_code`
- `notes`

#### `contribution_review_started`
Minimum payload:
- `external_contribution_id`
- `stage_name`

#### `review_cycle_started`
Minimum payload:
- `external_contribution_id`
- `stage_name`

#### `contribution_review_completed`
Minimum payload:
- `contribution_unit_id`
- `review_cycle_id`
- `result`

#### `review_approved`
Minimum payload:
- `external_contribution_id`
- `review_id`
- `approved_at`
- `stage_name`

#### `review_changes_requested`
Minimum payload:
- `external_contribution_id`
- `review_id`
- `requested_at`
- `stage_name`

#### `rework_requested`
Minimum payload:
- `contribution_unit_id`
- `review_cycle_id`
- `reason_code`
- `is_blocking`

#### `rework_resolved`
Minimum payload:
- `contribution_unit_id`
- `review_cycle_id`
- `resolved_at`

#### `draft_integrated_ready`
Minimum payload:
- `proposal_id`
- `ready_at`
- `approved_section_count`
- `total_section_count`

### Compliance and submission reliability

#### `compliance_gate_opened`
Minimum payload:
- `gate_id`
- `gate_type`

#### `compliance_gate_passed`
Minimum payload:
- `gate_id`
- `passed_at`

#### `compliance_gate_failed`
Minimum payload:
- `gate_id`
- `failed_at`
- `reason_code`

#### `compliance_gate_rework_requested`
Minimum payload:
- `gate_id`
- `requested_at`
- `external_rework_id`
- `reason_code`
- `notes`

#### `tender_submitted`
Minimum payload:
- `submitted_at`
- `channel`

#### `submission_acknowledged`
Minimum payload:
- `proposal_id`
- `occurred_at`
- `channel`
- `reference_id`

#### `submission_failed`
Minimum payload:
- `proposal_id`
- `occurred_at`
- `channel`
- `error_code`
- `error_message`

#### `clarification_requested`
Minimum payload:
- `request_id`
- `request_summary`
- `deadline_at`
- `source_label`

#### `clarification_response_drafted`
Minimum payload:
- `request_id`
- `response_summary`
- `source_label`

#### `clarification_submitted`
Minimum payload:
- `request_id`
- `response_summary`
- `source_label`

#### `clarification_closed`
Minimum payload:
- `request_id`
- `response_summary`
- `source_label`

### Terminal outcomes

#### `award_confirmed`
Minimum payload:
- `outcome`
- `recorded_at`

#### `award_details_recorded`
Minimum payload:
- `outcome`
- `recorded_at`
- `notes`

#### `loss_reason_recorded`
Minimum payload:
- `outcome`
- `recorded_at`
- `reason_code`
- `notes`

#### `tender_excluded`
Minimum payload:
- `outcome`
- `recorded_at`
- `reason_code`
- `notes`

#### `tender_withdrawn`
Minimum payload:
- `outcome`
- `recorded_at`
- `reason_code`
- `notes`

#### `tender_stopped`
Minimum payload:
- `outcome`
- `recorded_at`
- `reason_code`
- `notes`

#### `tender_stopped_at_gate`
Explicitly closes the tender from the compliance gate corridor without passing through submission.
Minimum payload:
- `outcome`
- `recorded_at`
- `gate_id`
- `reason_code`
- `notes`

## Idempotency Rules

- Emitters must treat `event_type`, `external_tender_id`, `occurred_at`, `source`, and payload identity keys as the logical uniqueness boundary until a dedicated event id is introduced.
- KPI ingestion must stay replay-safe and idempotent.
- Backfill and replay must preserve the distinction between `observed`, `inferred`, and `reconstructed` analytical facts.

## Timestamp Rules

- `occurred_at` is always UTC.
- `occurred_at` expresses business time, not transport time.
- If the source only knows ingestion time, that limitation must be explicit in payload metadata.
