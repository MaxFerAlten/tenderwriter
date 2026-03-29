from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PhaseTransitionDriver:
    from_state: str
    to_state: str
    occurred_at: datetime | None
    cause: str
    confidence: float
    source_event_type: str | None = None
    source_type: str = 'unknown'
    related_entity_id: str | None = None


@dataclass(slots=True)
class RequirementTransitionDriver:
    external_requirement_id: str
    summary: str | None
    priority: str | None
    compliance_status: str | None
    mapped_section_id: str | None
    mapped_section_title: str | None
    section_status: str | None
    driver_phase: str | None
    driver: str
    last_event_type: str | None = None


@dataclass(slots=True)
class TransitionSnapshot:
    summary: str
    items: list[PhaseTransitionDriver]
    requirement_items: list[RequirementTransitionDriver]


_PHASE_EVENT_RULES = {
    'tender_document_ingested': ('S0', 'S1'),
    'go_decision_recorded': ('S1', 'S2'),
    'no_bid_decision_recorded': ('S1', 'S13'),
    'bid_plan_created': ('S2', 'S2'),
    'bid_plan_approved': ('S2', 'S2'),
    'contribution_request_wave_opened': ('S2', 'S3'),
    'contribution_assignment_confirmed': ('S3', 'S3'),
    'contribution_received': ('S3', 'S4'),
    'contribution_review_started': ('S4', 'S5'),
    'review_cycle_started': ('S4', 'S5'),
    'review_approved': ('S5', 'S7'),
    'review_changes_requested': ('S5', 'S6'),
    'rework_requested': ('S5', 'S6'),
    'rework_resolved': ('S6', 'S5'),
    'coordination_risk_raised': ('S4', 'S6'),
    'rework_reescalated_to_coordination': ('S6', 'S4'),
    'draft_integrated_ready': ('S5', 'S7'),
    'compliance_gate_opened': ('S7', 'S8'),
    'compliance_gate_failed': ('S8', 'S8'),
    'compliance_gate_passed': ('S8', 'S7'),
    'compliance_gate_rework_requested': ('S8', 'S6'),
    'tender_submitted': ('S8', 'S9'),
    'submission_acknowledged': ('S9', 'S9'),
    'submission_failed': ('S9', 'S8'),
    'clarification_requested': ('S9', 'S10'),
    'clarification_response_drafted': ('S10', 'S10'),
    'clarification_submitted': ('S10', 'S10'),
    'clarification_closed': ('S10', 'S9'),
    'tender_stopped_at_gate': ('S8', 'S13'),
}
_TERMINAL_EVENT_TARGETS = {
    'award_confirmed': 'S11',
    'loss_reason_recorded': 'S12',
    'tender_excluded': 'S13',
    'tender_withdrawn': 'S13',
    'tender_stopped': 'S13',
}

def _normalized(value: Any) -> str:
    return str(value or '').strip().casefold()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace('Z', '+00:00')
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get('payload') or {}
    if isinstance(payload, dict) and isinstance(payload.get('payload'), dict):
        return payload['payload']
    return payload if isinstance(payload, dict) else {}


def _latest_event(events: list[dict[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
    for event in reversed(events):
        if _normalized(event.get('event_type')) in event_types:
            return event
    return None


def _clarification_active(events: list[dict[str, Any]]) -> bool:
    named_clarifications: dict[str, bool] = {}
    unnamed_open_count = 0

    for event in events:
        event_type = _normalized(event.get('event_type'))
        if event_type not in {
            'clarification_requested',
            'clarification_response_drafted',
            'clarification_submitted',
            'clarification_closed',
        }:
            continue

        payload = _event_payload(event)
        request_id = payload.get('request_id')
        normalized_request_id = str(request_id).strip() if request_id is not None else ''
        is_open_event = event_type != 'clarification_closed'

        if normalized_request_id:
            named_clarifications[normalized_request_id] = is_open_event
            continue

        if is_open_event:
            unnamed_open_count += 1
        else:
            unnamed_open_count = max(0, unnamed_open_count - 1)

    return unnamed_open_count > 0 or any(named_clarifications.values())


def _resolve_phase_transition(
    event_type: str,
    *,
    current_state: str | None,
) -> tuple[str, str] | None:
    static_transition = _PHASE_EVENT_RULES.get(event_type)
    if static_transition is not None:
        return static_transition

    terminal_target = _TERMINAL_EVENT_TARGETS.get(event_type)
    if terminal_target is not None:
        from_state = 'S10' if current_state == 'S10' else 'S9'
        return (from_state, terminal_target)

    return None


def _section_lookup(tender: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get('external_section_id')): section
        for section in list(tender.get('section_contexts') or [])
        if section.get('external_section_id') is not None
    }


def _build_phase_cause(event_type: str, payload: dict[str, Any]) -> tuple[str, str | None]:
    if event_type == 'tender_document_ingested':
        document_id = payload.get('document_id')
        filename = payload.get('filename') or 'uploaded tender dossier'
        return (
            f"Document {filename} was ingested into the mirrored tender workflow, opening the explicit governance corridor.",
            str(document_id) if document_id else None,
        )

    if event_type in {'contribution_review_started', 'review_cycle_started'}:
        stage_name = payload.get('stage_name') or 'review'
        contribution_id = payload.get('external_contribution_id')
        return (
            f"Review cycle '{stage_name}' started for contribution {contribution_id or 'n/a'}, pushing the tender into quality review.",
            str(contribution_id) if contribution_id else None,
        )

    if event_type == 'rework_requested':
        severity = _normalized(payload.get('severity')) or 'medium'
        blocking = 'blocking ' if payload.get('is_blocking') else ''
        reason = payload.get('reason') or 'clarifications are still required'
        contribution_id = payload.get('external_contribution_id')
        return (
            f"A {blocking}rework ({severity}) was opened for contribution {contribution_id or 'n/a'} because {reason}.",
            str(contribution_id) if contribution_id else None,
        )

    if event_type == 'rework_resolved':
        contribution_id = payload.get('external_contribution_id')
        return (
            f"Rework for contribution {contribution_id or 'n/a'} was resolved, allowing the tender to move back toward review/integration.",
            str(contribution_id) if contribution_id else None,
        )

    if event_type == 'coordination_risk_raised':
        contribution_id = payload.get('external_contribution_id')
        reason_code = payload.get('reason_code') or payload.get('notes') or 'coordination risk remains unresolved'
        return (
            f"Coordination risk was raised for contribution {contribution_id or 'n/a'} because {reason_code}.",
            str(contribution_id) if contribution_id else None,
        )

    if event_type == 'rework_reescalated_to_coordination':
        contribution_id = payload.get('external_contribution_id')
        reason_code = payload.get('reason_code') or payload.get('notes') or 'the item needs renewed orchestration before another review cycle'
        return (
            f"Rework for contribution {contribution_id or 'n/a'} was pushed back to coordination because {reason_code}.",
            str(contribution_id) if contribution_id else None,
        )

    if event_type == 'compliance_gate_opened':
        gate_name = payload.get('gate_name') or 'compliance gate'
        gate_id = payload.get('external_gate_id')
        return (
            f"Gate '{gate_name}' was opened, so the tender entered compliance-gate control.",
            str(gate_id) if gate_id else None,
        )

    if event_type == 'compliance_gate_failed':
        gate_name = payload.get('gate_name') or 'compliance gate'
        notes = payload.get('decision_notes') or 'unresolved compliance issues remain'
        gate_id = payload.get('external_gate_id')
        return (
            f"Gate '{gate_name}' failed because {notes}.",
            str(gate_id) if gate_id else None,
        )

    if event_type == 'compliance_gate_passed':
        gate_name = payload.get('gate_name') or 'compliance gate'
        gate_id = payload.get('external_gate_id')
        return (
            f"Gate '{gate_name}' passed, so compliance blocking conditions were cleared.",
            str(gate_id) if gate_id else None,
        )

    if event_type == 'compliance_gate_rework_requested':
        gate_name = payload.get('gate_name') or 'compliance gate'
        reason_code = payload.get('reason_code') or payload.get('notes') or 'the gate requires another blocking rework cycle'
        gate_id = payload.get('external_gate_id')
        return (
            f"Gate '{gate_name}' sent the tender back into rework because {reason_code}.",
            str(gate_id) if gate_id else None,
        )

    if event_type == 'go_decision_recorded':
        decision = payload.get('decision') or 'go'
        return (f"Tender decision '{decision}' was recorded, moving the workflow into formal bid planning.", str(payload.get('decision') or decision))

    if event_type == 'no_bid_decision_recorded':
        reason_code = payload.get('reason_code') or 'no-bid'
        return (f"Tender was explicitly marked as no-bid with reason {reason_code}.", str(reason_code))

    if event_type == 'bid_plan_created':
        plan_status = payload.get('plan_status') or 'created'
        return (f"Bid plan entered status '{plan_status}', so the tender moved into planning.", str(plan_status))

    if event_type == 'bid_plan_approved':
        return ('Bid plan was approved and remains inside the planning corridor.', str(payload.get('plan_status') or 'approved'))

    if event_type == 'contribution_request_wave_opened':
        count = payload.get('contribution_count') or 'n/a'
        return (f"A contribution request wave covering {count} contributions was opened.", str(count))

    if event_type == 'contribution_assignment_confirmed':
        return ('Contribution assignment was confirmed for the current request wave.', str(payload.get('external_contribution_id') or 'assignment'))

    if event_type == 'contribution_received':
        contribution_id = payload.get('external_contribution_id')
        request_id = payload.get('external_request_id')
        return (
            f"Contribution {contribution_id or 'n/a'} was received, so execution moved beyond request orchestration into active drafting.",
            str(contribution_id or request_id) if contribution_id or request_id else None,
        )

    if event_type == 'review_approved':
        contribution_id = payload.get('external_contribution_id')
        return (f"Contribution {contribution_id or 'n/a'} completed review with outcome approved.", str(contribution_id) if contribution_id else None)

    if event_type == 'review_changes_requested':
        contribution_id = payload.get('external_contribution_id')
        return (f"Contribution {contribution_id or 'n/a'} completed review with changes requested.", str(contribution_id) if contribution_id else None)

    if event_type == 'draft_integrated_ready':
        proposal_id = payload.get('proposal_id')
        return (f"Proposal {proposal_id or 'n/a'} was marked as draft integrated ready for the final gate.", str(proposal_id) if proposal_id else None)
    if event_type == 'tender_submitted':
        return ('Tender submission was recorded in the workflow telemetry.', None)

    if event_type == 'clarification_requested':
        request_id = payload.get('request_id')
        summary = payload.get('request_summary') or 'a post-submission clarification was requested'
        return (
            f"Post-submission clarification {request_id or 'n/a'} was requested because {summary}.",
            str(request_id) if request_id else None,
        )

    if event_type == 'submission_acknowledged':
        reference_id = payload.get('reference_id')
        return (f"Submission was acknowledged by the target channel with reference {reference_id or 'n/a'}.", str(reference_id) if reference_id else None)

    if event_type == 'submission_failed':
        error_code = payload.get('error_code') or 'submission_failed'
        return (f"Submission failed on channel {payload.get('channel') or 'n/a'} with error {error_code}.", str(error_code))

    if event_type == 'clarification_response_drafted':
        request_id = payload.get('request_id')
        return (f"Draft response for clarification {request_id or 'n/a'} was prepared.", str(request_id) if request_id else None)
    if event_type == 'clarification_submitted':
        request_id = payload.get('request_id')
        return (f"Clarification {request_id or 'n/a'} was submitted back to the buyer workflow.", str(request_id) if request_id else None)

    if event_type == 'clarification_closed':
        request_id = payload.get('request_id')
        return (f"Clarification {request_id or 'n/a'} was closed in the post-submission workflow.", str(request_id) if request_id else None)

    if event_type == 'award_confirmed':
        return ('Award confirmation moved the tender into the win terminal state.', str(payload.get('outcome') or 'won'))

    if event_type == 'loss_reason_recorded':
        return ('Loss reason was recorded, closing the tender in the loss terminal state.', str(payload.get('reason_code') or payload.get('outcome') or 'lost'))

    if event_type == 'tender_excluded':
        return ('Tender was excluded from the competition and entered the stop terminal state.', str(payload.get('reason_code') or 'excluded'))

    if event_type == 'tender_withdrawn':
        return ('Tender was withdrawn strategically and entered the stop terminal state.', str(payload.get('reason_code') or 'withdrawn'))

    if event_type == 'tender_stopped':
        return ('Tender was stopped and entered the terminal stop state.', str(payload.get('reason_code') or 'stopped'))

    if event_type == 'tender_stopped_at_gate':
        gate_name = payload.get('gate_name') or 'compliance gate'
        reason_code = payload.get('reason_code') or payload.get('notes') or 'the gate was intentionally closed without continuing the tender'
        gate_id = payload.get('external_gate_id')
        return (
            f"Tender was stopped directly from gate '{gate_name}' because {reason_code}.",
            str(gate_id) if gate_id else None,
        )
    return ('Operational transition recorded.', None)


def _build_phase_items(events: list[dict[str, Any]], analytical_phase: str | None) -> list[PhaseTransitionDriver]:
    resolved_items: list[PhaseTransitionDriver] = []
    current_state: str | None = None
    for event in events:
        event_type = _normalized(event.get('event_type'))
        transition = _resolve_phase_transition(event_type, current_state=current_state)
        if transition is None:
            continue
        from_state, to_state = transition
        payload = _event_payload(event)
        cause, related_entity_id = _build_phase_cause(event_type, payload)
        resolved_items.append(
            PhaseTransitionDriver(
                from_state=from_state,
                to_state=to_state,
                occurred_at=_parse_datetime(event.get('occurred_at')),
                cause=cause,
                confidence=0.9,
                source_event_type=event_type,
                source_type='observed',
                related_entity_id=related_entity_id,
            )
        )
        current_state = to_state

    if resolved_items:
        return list(reversed(resolved_items[-8:]))

    if analytical_phase == 'S1':
        return [
            PhaseTransitionDriver(
                from_state='S0',
                to_state='S1',
                occurred_at=None,
                cause='The tender dossier is mirrored and awaiting an explicit go/no-go decision.',
                confidence=0.62,
                source_event_type='inferred_from_lifecycle_state',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S2':
        return [
            PhaseTransitionDriver(
                from_state='S1',
                to_state='S2',
                occurred_at=None,
                cause='Bid-planning metadata indicates the tender has moved into formal planning.',
                confidence=0.62,
                source_event_type='inferred_from_bid_plan',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S3':
        return [
            PhaseTransitionDriver(
                from_state='S2',
                to_state='S3',
                occurred_at=None,
                cause='Contribution-wave metadata indicates requests are being orchestrated for departments.',
                confidence=0.62,
                source_event_type='inferred_from_request_wave',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S5':
        return [
            PhaseTransitionDriver(
                from_state='S4',
                to_state='S5',
                occurred_at=None,
                cause='The mirrored section state indicates active review, even though no explicit review-start event is available.',
                confidence=0.62,
                source_event_type='inferred_from_section_status',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S6':
        return [
            PhaseTransitionDriver(
                from_state='S5',
                to_state='S6',
                occurred_at=None,
                cause='Blocking rework is still reflected in the mirrored workflow state.',
                confidence=0.62,
                source_event_type='inferred_from_rework_state',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S7':
        return [
            PhaseTransitionDriver(
                from_state='S5',
                to_state='S7',
                occurred_at=None,
                cause='Integrated-draft readiness is reflected in the mirrored workflow state.',
                confidence=0.62,
                source_event_type='inferred_from_draft_ready',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S8':
        return [
            PhaseTransitionDriver(
                from_state='S7',
                to_state='S8',
                occurred_at=None,
                cause='Compliance gate pressure is reflected in the mirrored operational state.',
                confidence=0.62,
                source_event_type='inferred_from_gate_state',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S9':
        return [
            PhaseTransitionDriver(
                from_state='S8',
                to_state='S9',
                occurred_at=None,
                cause='Submission state is reflected in the mirrored lifecycle metadata.',
                confidence=0.62,
                source_event_type='inferred_from_submission_state',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S10':
        return [
            PhaseTransitionDriver(
                from_state='S9',
                to_state='S10',
                occurred_at=None,
                cause='Post-submission clarification pressure is being inferred from the mirrored workflow state.',
                confidence=0.62,
                source_event_type='inferred_from_clarification_state',
                source_type='inferred',
            )
        ]
    if analytical_phase == 'S13':
        inferred_from_state = 'S10' if _clarification_active(events) else 'S9'
        inferred_cause = (
            'Terminal stop, loss or exclusion state is reflected after an active clarification loop.'
            if inferred_from_state == 'S10'
            else 'Terminal stop or exclusion state is reflected in the mirrored lifecycle metadata.'
        )
        return [
            PhaseTransitionDriver(
                from_state=inferred_from_state,
                to_state='S13',
                occurred_at=None,
                cause=inferred_cause,
                confidence=0.62,
                source_event_type='inferred_from_terminal_state',
                source_type='inferred',
            )
        ]
    return []

def _requirement_driver(
    requirement: dict[str, Any],
    *,
    section_lookup: dict[str, dict[str, Any]],
    analytical_phase: str | None,
    latest_review_event: dict[str, Any] | None,
    latest_rework_event: dict[str, Any] | None,
    latest_gate_event: dict[str, Any] | None,
) -> RequirementTransitionDriver:
    mapped_section_id = requirement.get('mapped_section_id')
    section = section_lookup.get(str(mapped_section_id)) if mapped_section_id else None
    section_status = _normalized(section.get('status')) if section else None
    compliance_status = _normalized(requirement.get('compliance_status')) or None

    driver_phase = 'S4'
    driver = 'Requirement progress is being inferred from the current proposal section state.'
    last_event_type = None

    latest_gate_event_type = _normalized((latest_gate_event or {}).get('event_type')) or None
    latest_rework_event_type = _normalized((latest_rework_event or {}).get('event_type')) or None

    if not mapped_section_id:
        driver_phase = 'S3'
        driver = 'Requirement was extracted but is not mapped to any proposal section yet.'
        last_event_type = 'requirements_extracted'
    elif latest_gate_event_type in {'compliance_gate_opened', 'compliance_gate_failed'} and compliance_status != 'fully_addressed':
        driver_phase = 'S8'
        gate_payload = _event_payload(latest_gate_event or {})
        gate_status = _normalized(gate_payload.get('status')) or 'open'
        gate_name = gate_payload.get('gate_name') or 'Auto compliance readiness'
        driver = f"Requirement remains unresolved while gate '{gate_name}' is {gate_status}."
        last_event_type = latest_gate_event_type or 'compliance_gate_opened'
    elif latest_rework_event_type == 'rework_requested' and compliance_status != 'fully_addressed':
        driver_phase = 'S6'
        rework_payload = _event_payload(latest_rework_event or {})
        reason = rework_payload.get('reason') or 'blocking changes are still open'
        driver = f"Requirement is inside a rework loop because {reason}."
        last_event_type = latest_rework_event_type or 'rework_requested'
    elif section_status == 'in_review' or analytical_phase == 'S5':
        driver_phase = 'S5'
        stage_name = _event_payload(latest_review_event or {}).get('stage_name') or 'review'
        driver = f"Mapped section '{section.get('title') or mapped_section_id}' is in {stage_name}, so the requirement is still under review."
        last_event_type = _normalized((latest_review_event or {}).get('event_type')) or 'contribution_review_started'
    elif section_status == 'approved' and compliance_status == 'fully_addressed':
        driver_phase = 'S7'
        driver = f"Mapped section '{section.get('title') or mapped_section_id}' is approved and the requirement is fully addressed."
        last_event_type = 'proposal_section_updated'
    elif section_status in {'in_progress', 'draft', 'todo'}:
        driver_phase = 'S4'
        driver = f"Mapped section '{section.get('title') or mapped_section_id}' is still in progress, so the requirement is not yet stabilized."
        last_event_type = 'proposal_section_updated'

    return RequirementTransitionDriver(
        external_requirement_id=str(requirement.get('external_requirement_id') or 'unknown'),
        summary=requirement.get('summary'),
        priority=requirement.get('priority'),
        compliance_status=compliance_status,
        mapped_section_id=str(mapped_section_id) if mapped_section_id is not None else None,
        mapped_section_title=section.get('title') if section else None,
        section_status=section_status,
        driver_phase=driver_phase,
        driver=driver,
        last_event_type=last_event_type,
    )


def build_transition_snapshot(
    tender: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    analytical_phase: str | None,
) -> TransitionSnapshot:
    section_lookup = _section_lookup(tender)
    latest_review_event = _latest_event(events, {'contribution_review_started', 'review_cycle_started'})
    latest_rework_event = _latest_event(events, {'rework_requested', 'rework_resolved'})
    latest_gate_event = _latest_event(events, {'compliance_gate_opened', 'compliance_gate_failed', 'compliance_gate_passed'})
    phase_items = _build_phase_items(events, analytical_phase)
    requirements = list(tender.get('requirement_contexts') or [])
    requirement_items = [
        _requirement_driver(
            requirement,
            section_lookup=section_lookup,
            analytical_phase=analytical_phase,
            latest_review_event=latest_review_event,
            latest_rework_event=latest_rework_event,
            latest_gate_event=latest_gate_event,
        )
        for requirement in requirements
    ]
    requirement_items.sort(
        key=lambda item: (
            0 if item.driver_phase in {'S8', 'S6', 'S5'} else 1,
            0 if _normalized(item.priority) == 'high' else 1 if _normalized(item.priority) == 'medium' else 2,
            item.external_requirement_id,
        )
    )

    leading_phase = phase_items[0].to_state if phase_items else requirement_items[0].driver_phase if requirement_items else analytical_phase

    if not phase_items and not requirement_items:
        summary = 'No transition evidence is available yet for this tender.'
    elif leading_phase in {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13'} and analytical_phase and analytical_phase != leading_phase:
        summary = f'Latest mirrored driver points to {leading_phase} while the current analytical phase remains {analytical_phase}.'
    elif leading_phase in {'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13'}:
        summary = f'Current transition pressure is centered on {leading_phase}, backed by mirrored workflow events and requirement-level drivers.'
    else:
        summary = 'Recent workflow events and requirement mappings are available for transition analysis.'

    return TransitionSnapshot(summary=summary, items=phase_items, requirement_items=requirement_items)



