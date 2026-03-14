# Canonical Event Catalog

This document freezes the canonical event envelope and first event families for `tw-kpi-reason-engine`.

## Event Envelope

Every event sent to the KPI engine must provide the following fields:

- `event_type`: stable domain event identifier.
- `external_tender_id`: cross-service tender identifier.
- `occurred_at`: UTC timestamp representing when the domain event actually happened.
- `actor_id`: optional actor that triggered the event.
- `source`: emitting subsystem, for example `tw-backend` or `admin-ui`.
- `schema_version`: payload schema version for forward evolution.
- `payload`: event-specific data.

## Base Domain Events

### tender_created
Created when a tender is registered in the platform.
Payload minimum:
- `title`
- `customer_name`
- `due_at`

### tender_document_ingested
Created when a tender document or attachment becomes available to the workflow.
Payload minimum:
- `document_id`
- `document_type`
- `filename`

### requirements_extracted
Created when structured requirements are extracted from source documents.
Payload minimum:
- `requirement_count`
- `extractor_version`

### proposal_created
Created when the proposal structure is initialized.
Payload minimum:
- `proposal_id`
- `section_count`

### proposal_section_updated
Created when a tracked proposal section changes in a meaningful way.
Payload minimum:
- `external_section_id`
- `change_type`
- `status`

### tender_submitted
Created when the tender is officially submitted.
Payload minimum:
- `submitted_at`
- `channel`

### tender_outcome_recorded
Created when the business outcome is known.
Payload minimum:
- `outcome`
- `recorded_at`

## Operational Events

### contribution_request_created
Raised when a contribution unit is opened for an owner or department.
Payload minimum:
- `contribution_unit_id`
- `department_id`
- `due_at`

### contribution_due_date_set
Raised when the expected due date changes.
Payload minimum:
- `contribution_unit_id`
- `due_at`

### contribution_received
Raised when an owner delivers a contribution.
Payload minimum:
- `contribution_unit_id`
- `received_at`
- `delivery_type`

### contribution_review_completed
Raised when a review cycle ends.
Payload minimum:
- `contribution_unit_id`
- `review_cycle_id`
- `result`

### rework_requested
Raised when review or compliance requires rework.
Payload minimum:
- `contribution_unit_id`
- `review_cycle_id`
- `reason_code`

### rework_resolved
Raised when the rework loop is closed.
Payload minimum:
- `contribution_unit_id`
- `review_cycle_id`
- `resolved_at`

### compliance_gate_opened
Raised when a formal compliance gate starts.
Payload minimum:
- `gate_id`
- `gate_type`

### compliance_gate_passed
Raised when a compliance gate succeeds.
Payload minimum:
- `gate_id`
- `passed_at`

### compliance_gate_failed
Raised when a compliance gate fails.
Payload minimum:
- `gate_id`
- `failed_at`
- `reason_code`

### call_scheduled
Raised when a tender coordination call is planned.
Payload minimum:
- `call_id`
- `scheduled_at`

### call_attendance_recorded
Raised when attendance is registered for a call.
Payload minimum:
- `call_id`
- `participant_id`
- `attendance_status`

### sla_breached
Raised when an SLA target or maximum threshold is violated.
Payload minimum:
- `sla_subject_id`
- `sla_code`
- `breached_at`

## Idempotency Rules

- The emitting system must treat `event_type`, `external_tender_id`, `occurred_at`, `source`, and payload identity keys as the logical uniqueness boundary until a dedicated event id is introduced.
- The KPI engine ingestion layer must be implemented as idempotent and safe to replay.
- Retries from `tw-backend` must not create duplicate analytical facts.

## Timestamp Rules

- `occurred_at` must be expressed in UTC.
- `occurred_at` represents business occurrence time, not transport or ingestion time.
- If a source system only knows ingestion time, that limitation must be explicit in the payload metadata.
