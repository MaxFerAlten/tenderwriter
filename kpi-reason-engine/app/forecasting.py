from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.contract import (
    FORECAST_DECISION_BUNDLE_VERSION,
    FORECAST_OUTPUT_SCHEMA_VERSION,
    FORECAST_HEURISTIC_ENGINE,
    FORECAST_MARKOV_ENGINE,
    HEURISTIC_FORECAST_VERSION,
    MARKOV_ABSORBING_STATES,
    MARKOV_BACKTEST_VERSION,
    MARKOV_BUNDLE_KIND,
    MARKOV_MIN_CURRENT_STATE_SUPPORT,
    MARKOV_MIN_TOTAL_TRANSITIONS,
    MARKOV_MODEL_VERSION,
    MARKOV_POSITIVE_STATES,
    MARKOV_STATE_SCOPE,
)


@dataclass(slots=True)
class ForecastScenarioData:
    name: str
    probability: float | None
    description: str | None
    confidence: float | None
    drivers: list[str]
    recommended_action: str | None


@dataclass(slots=True)
class ForecastDecisionActionData:
    code: str
    title: str
    priority: str
    rationale: str
    expected_impact: str | None
    confidence: float | None
    drivers: list[str]


@dataclass(slots=True)
class ForecastSnapshot:
    summary: str
    overall_confidence: float | None
    scenarios: list[ForecastScenarioData]
    next_best_actions: list[ForecastDecisionActionData]
    analysis_metadata: dict[str, Any]


_PHASE_LABELS = {
    'S0': 'Intake Opportunity',
    'S1': 'Go / No-Go',
    'S2': 'Bid Planning',
    'S3': 'Request Contributions',
    'S4': 'Coordination & Collection',
    'S5': 'Quality / Technical Review',
    'S6': 'Rework / Clarifications',
    'S7': 'Integrated Draft',
    'S8': 'Compliance Gate',
    'S9': 'Submission',
    'S10': 'Post-Submission Clarifications',
    'S11': 'Win',
    'S12': 'Loss',
    'S13': 'Excluded / Withdrawn / No-Bid',
}

_TERMINAL_SCENARIOS = {
    'S11': ('win_locked', 'Tender outcome is already recorded as win.'),
    'S12': ('loss_locked', 'Tender outcome is already recorded as loss.'),
    'S13': ('stop_locked', 'Tender is already excluded, withdrawn or marked as no-bid.'),
}
_BASE_PROBABILITIES = {
    'S0': {'submit_on_time': 0.12, 'extended_rework': 0.28, 'pause_or_stop': 0.60},
    'S1': {'submit_on_time': 0.16, 'extended_rework': 0.24, 'pause_or_stop': 0.60},
    'S2': {'submit_on_time': 0.24, 'extended_rework': 0.42, 'pause_or_stop': 0.34},
    'S3': {'submit_on_time': 0.36, 'extended_rework': 0.44, 'pause_or_stop': 0.20},
    'S4': {'submit_on_time': 0.42, 'extended_rework': 0.40, 'pause_or_stop': 0.18},
    'S5': {'submit_on_time': 0.34, 'extended_rework': 0.51, 'pause_or_stop': 0.15},
    'S6': {'submit_on_time': 0.24, 'extended_rework': 0.58, 'pause_or_stop': 0.18},
    'S7': {'submit_on_time': 0.62, 'extended_rework': 0.26, 'pause_or_stop': 0.12},
    'S8': {'submit_on_time': 0.46, 'extended_rework': 0.40, 'pause_or_stop': 0.14},
    'S9': {'submit_on_time': 0.78, 'extended_rework': 0.14, 'pause_or_stop': 0.08},
    'S10': {'submit_on_time': 0.68, 'extended_rework': 0.20, 'pause_or_stop': 0.12},
}
_SCENARIO_DESCRIPTIONS = {
    'submit_on_time': 'The tender is likely to stay on the delivery path and reach the submission corridor without major detours.',
    'extended_rework': 'The tender is likely to keep circulating through review, clarification or compliance work before it can stabilize.',
    'pause_or_stop': 'The tender may be paused, de-scoped or stopped if the current risk picture does not improve.',
}


def _phase_label(phase: str) -> str:
    return _PHASE_LABELS.get(phase, phase)


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


def _days_until(due_at: datetime | None, now: datetime) -> float | None:
    if due_at is None:
        return None
    return (due_at - now).total_seconds() / 86400


def _score_value(snapshot_record: dict[str, Any], kpi_code: str) -> float | None:
    for item in snapshot_record.get('kpis', []):
        if str(item.get('kpi_code')) == kpi_code:
            value = item.get('value')
            return None if value is None else float(value)
    return None


def _normalize_probabilities(values: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.0, value) for key, value in values.items()}
    total = sum(cleaned.values())
    if total <= 0:
        equal_value = round(1.0 / max(1, len(cleaned)), 3)
        normalized = {key: equal_value for key in cleaned}
    else:
        normalized = {key: round(value / total, 3) for key, value in cleaned.items()}
    delta = round(1.0 - sum(normalized.values()), 3)
    first_key = next(iter(normalized))
    normalized[first_key] = round(normalized[first_key] + delta, 3)
    return normalized


def _scenario_action(name: str) -> str:
    if name == 'submit_on_time':
        return 'Protect the current submission corridor and keep high-risk blockers from re-opening.'
    if name == 'extended_rework':
        return 'Prioritize blocker closure and compress the review loop before the next gate.'
    if name == 'pause_or_stop':
        return 'Escalate viability immediately and decide whether to re-scope or stop the tender.'
    if name == 'win_locked':
        return 'Shift to post-award mobilization and preserve the analytical trace for audit.'
    if name == 'loss_locked':
        return 'Archive the loss drivers and feed them into retrospective learning.'
    return 'Keep monitoring the tender trajectory and update the latest analytical snapshot when new events arrive.'


def _rollout_metadata() -> dict[str, Any]:
    return {
        'rollout_policy': settings.normalized_rollout_policy,
        'shadow_rollout_enabled': settings.semantic_shadow_rollout_enabled,
        'markov_rollout_enabled': settings.markov_rollout_enabled,
        'calibrated_forecast_enabled': settings.markov_rollout_enabled,
        'shadow_mode_enabled': settings.semantic_shadow_rollout_enabled,
        'forecast_output_schema_version': FORECAST_OUTPUT_SCHEMA_VERSION,
    }


def _sample_weight(source_type: str) -> float:
    if source_type == 'reconstructed':
        return 0.55
    if source_type == 'inferred':
        return 0.75
    return 1.0

def _group_markov_sequences(history_points: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in history_points:
        external_tender_id = str(item.get('external_tender_id') or '')
        phase = str(item.get('analytical_phase') or '')
        if not external_tender_id or phase not in MARKOV_STATE_SCOPE:
            continue
        grouped[external_tender_id].append(item)

    sequences: list[list[dict[str, Any]]] = []
    for items in grouped.values():
        ordered = sorted(
            items,
            key=lambda item: (
                str(item.get('generated_at') or ''),
                int(item.get('snapshot_id') or 0),
            ),
        )
        compressed: list[dict[str, Any]] = []
        for item in ordered:
            phase = str(item.get('analytical_phase') or '')
            if phase not in MARKOV_STATE_SCOPE:
                continue
            normalized = {
                'external_tender_id': str(item.get('external_tender_id') or ''),
                'snapshot_id': int(item.get('snapshot_id') or 0),
                'generated_at': str(item.get('generated_at') or ''),
                'analytical_phase': phase,
                'source_type': str(item.get('source_type') or 'observed'),
            }
            if compressed and compressed[-1]['analytical_phase'] == phase:
                if compressed[-1]['source_type'] == 'reconstructed' and normalized['source_type'] != 'reconstructed':
                    compressed[-1] = normalized
                continue
            compressed.append(normalized)
        if compressed:
            sequences.append(compressed)
    return sequences


def _solve_hitting_probabilities(
    matrix: dict[str, dict[str, float]],
    *,
    target_states: set[str],
    blocker_states: set[str],
) -> dict[str, float]:
    values: dict[str, float] = {}
    for state in MARKOV_STATE_SCOPE:
        if state in target_states:
            values[state] = 1.0
        elif state in blocker_states:
            values[state] = 0.0
        else:
            values[state] = 0.0

    frozen_states = target_states | blocker_states
    for _ in range(96):
        updated = dict(values)
        max_delta = 0.0
        for state in MARKOV_STATE_SCOPE:
            if state in frozen_states:
                continue
            row = matrix.get(state)
            if not row:
                continue
            next_value = sum(probability * values.get(next_state, 0.0) for next_state, probability in row.items())
            updated[state] = next_value
            max_delta = max(max_delta, abs(next_value - values[state]))
        values = updated
        if max_delta < 1e-6:
            break
    return values


def _submission_outcome(sequence: list[dict[str, Any]]) -> float | None:
    for item in sequence:
        phase = str(item.get('analytical_phase') or '')
        if phase in MARKOV_POSITIVE_STATES:
            return 1.0
        if phase == 'S13':
            return 0.0
    return None


def _build_backtest_metrics(
    sequences: list[list[dict[str, Any]]],
    matrix: dict[str, dict[str, float]],
    submit_probabilities: dict[str, float],
) -> dict[str, Any]:
    samples: list[tuple[str, float, float]] = []
    phase_support: Counter[str] = Counter()
    for sequence in sequences:
        actual_submit = _submission_outcome(sequence)
        if actual_submit is None:
            continue
        for item in sequence:
            phase = str(item.get('analytical_phase') or '')
            if phase in MARKOV_POSITIVE_STATES or phase in MARKOV_ABSORBING_STATES:
                break
            if phase not in matrix:
                continue
            predicted_submit = float(submit_probabilities.get(phase, 0.0))
            samples.append((phase, predicted_submit, actual_submit))
            phase_support[phase] += 1

    if not samples:
        return {
            'version': MARKOV_BACKTEST_VERSION,
            'sample_count': 0,
            'submission_accuracy': None,
            'calibration_gap': None,
            'dominant_phase': None,
        }

    correct = sum(1 for _, predicted, actual in samples if (predicted >= 0.5 and actual == 1.0) or (predicted < 0.5 and actual == 0.0))
    calibration_gap = sum(abs(predicted - actual) for _, predicted, actual in samples) / len(samples)
    dominant_phase = phase_support.most_common(1)[0][0] if phase_support else None
    return {
        'version': MARKOV_BACKTEST_VERSION,
        'sample_count': len(samples),
        'submission_accuracy': round(correct / len(samples), 2),
        'calibration_gap': round(calibration_gap, 2),
        'dominant_phase': dominant_phase,
    }


def _build_markov_bundle(history_points: list[dict[str, Any]]) -> dict[str, Any]:
    sequences = _group_markov_sequences(history_points)
    weighted_counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    raw_outgoing: dict[str, int] = defaultdict(int)
    source_mix: dict[str, int] = defaultdict(int)
    dataset_tenders = 0

    for sequence in sequences:
        if len(sequence) < 2:
            continue
        dataset_tenders += 1
        for previous, current in zip(sequence, sequence[1:]):
            from_state = str(previous.get('analytical_phase') or '')
            to_state = str(current.get('analytical_phase') or '')
            if from_state not in MARKOV_STATE_SCOPE or to_state not in MARKOV_STATE_SCOPE:
                continue
            source_type = 'reconstructed' if (
                previous.get('source_type') == 'reconstructed' or current.get('source_type') == 'reconstructed'
            ) else 'observed'
            weighted_counts[from_state][to_state] += _sample_weight(source_type)
            raw_outgoing[from_state] += 1
            source_mix[source_type] += 1

    matrix: dict[str, dict[str, float]] = {}
    for state in MARKOV_STATE_SCOPE:
        if state in MARKOV_ABSORBING_STATES:
            matrix[state] = {state: 1.0}
            continue
        row = weighted_counts.get(state)
        if not row:
            continue
        matrix[state] = _normalize_probabilities(dict(row))

    submit_probabilities = _solve_hitting_probabilities(
        matrix,
        target_states=set(MARKOV_POSITIVE_STATES),
        blocker_states={'S13'},
    )
    backtest = _build_backtest_metrics(sequences, matrix, submit_probabilities)
    covered_states = [state for state, count in raw_outgoing.items() if count > 0]
    non_absorbing_count = len([state for state in MARKOV_STATE_SCOPE if state not in MARKOV_ABSORBING_STATES])
    coverage_ratio = len(covered_states) / max(1, non_absorbing_count)

    return {
        'version': MARKOV_MODEL_VERSION,
        'bundle_kind': MARKOV_BUNDLE_KIND,
        'state_scope': list(MARKOV_STATE_SCOPE),
        'absorbing_states': list(MARKOV_ABSORBING_STATES),
        'positive_states': list(MARKOV_POSITIVE_STATES),
        'matrix': matrix,
        'raw_outgoing': dict(raw_outgoing),
        'sample_count': int(sum(raw_outgoing.values())),
        'dataset_tenders': dataset_tenders,
        'source_mix': dict(source_mix),
        'covered_states': covered_states,
        'coverage_ratio': round(coverage_ratio, 2),
        'submit_probabilities': submit_probabilities,
        'backtest': backtest,
    }


def _row_driver(phase: str, row: dict[str, float] | None) -> str:
    if not row:
        return f'Current phase {phase} has no empirical outgoing row in the Markov bundle yet.'
    ordered = sorted(row.items(), key=lambda item: item[1], reverse=True)
    top_entries = ', '.join(f"{state}:{probability:.2f}" for state, probability in ordered[:3])
    return f'Empirical row for {phase}: {top_entries}.'


def _project_path(phase: str, matrix: dict[str, dict[str, float]], max_steps: int = 7) -> list[str]:
    path = [phase]
    current = phase
    seen = {phase}
    for _ in range(max_steps):
        if current in MARKOV_ABSORBING_STATES:
            break
        row = matrix.get(current)
        if not row:
            break
        next_state = max(row.items(), key=lambda item: (item[1], item[0]))[0]
        path.append(next_state)
        if next_state in MARKOV_ABSORBING_STATES:
            break
        if next_state in seen:
            break
        seen.add(next_state)
        current = next_state
    return path


def _driver_scores(snapshot_record: dict[str, Any]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for code in ['A1', 'A4', 'B1', 'B2', 'B4', 'Q', 'E']:
        value = _score_value(snapshot_record, code)
        if value is not None:
            scores[code] = round(value, 1)
    return scores


def _driver_lines(driver_scores: dict[str, float], due_days: float | None) -> list[str]:
    lines: list[str] = []
    if 'A1' in driver_scores:
        lines.append(f"A1 requirement coverage is {driver_scores['A1']:.1f}.")
    if 'A4' in driver_scores:
        lines.append(f"A4 compliance resilience is {driver_scores['A4']:.1f}.")
    if 'B1' in driver_scores:
        lines.append(f"B1 deadline discipline is {driver_scores['B1']:.1f}.")
    if 'B2' in driver_scores:
        lines.append(f"B2 responsiveness is {driver_scores['B2']:.1f}.")
    if 'B4' in driver_scores:
        lines.append(f"B4 contribution stability is {driver_scores['B4']:.1f}.")
    if due_days is not None:
        lines.append(f'Deadline buffer is {round(due_days, 1)} days.')
    return lines

def _apply_kpi_adjustments(
    probabilities: dict[str, float],
    *,
    driver_scores: dict[str, float],
    phase: str,
    due_days: float | None,
) -> tuple[dict[str, float], list[str], list[str]]:
    adjusted = dict(probabilities)
    notes: list[str] = []
    active_codes: list[str] = []

    def nudge(code: str, *, submit: float = 0.0, rework: float = 0.0, stop: float = 0.0, note: str) -> None:
        adjusted['submit_on_time'] += submit
        adjusted['extended_rework'] += rework
        adjusted['pause_or_stop'] += stop
        notes.append(note)
        if code not in active_codes:
            active_codes.append(code)

    a1 = driver_scores.get('A1')
    if a1 is not None:
        if a1 < 65:
            nudge('A1', submit=-0.08, rework=0.05, stop=0.03, note=f'A1 {a1:.1f} leaves material requirement gaps open.')
        elif a1 >= 80:
            nudge('A1', submit=0.05, rework=-0.03, stop=-0.02, note=f'A1 {a1:.1f} supports a cleaner coverage path.')

    a4 = driver_scores.get('A4')
    if a4 is not None:
        if a4 < 70:
            nudge('A4', submit=-0.09, rework=0.03, stop=0.06, note=f'A4 {a4:.1f} keeps compliance risk materially elevated.')
        elif a4 >= 82:
            nudge('A4', submit=0.05, rework=-0.02, stop=-0.03, note=f'A4 {a4:.1f} keeps the compliance corridor stable.')

    b1 = driver_scores.get('B1')
    if b1 is not None:
        if b1 < 60:
            nudge('B1', submit=-0.07, rework=0.03, stop=0.04, note=f'B1 {b1:.1f} shows deadline pressure that can stop the tender.')
        elif b1 >= 78:
            nudge('B1', submit=0.04, rework=-0.02, stop=-0.02, note=f'B1 {b1:.1f} indicates strong deadline discipline.')

    b2 = driver_scores.get('B2')
    if b2 is not None:
        if b2 < 65:
            nudge('B2', submit=-0.04, rework=0.07, stop=-0.03, note=f'B2 {b2:.1f} increases the probability of review and clarification loops.')
        elif b2 >= 78:
            nudge('B2', submit=0.03, rework=-0.03, stop=0.0, note=f'B2 {b2:.1f} limits operational lag in the current journey.')

    b4 = driver_scores.get('B4')
    if b4 is not None:
        if b4 < 65:
            nudge('B4', submit=-0.05, rework=0.08, stop=-0.03, note=f'B4 {b4:.1f} shows churn in the contribution loop.')
        elif b4 >= 78:
            nudge('B4', submit=0.03, rework=-0.03, stop=0.0, note=f'B4 {b4:.1f} shows the contribution set is stable.')

    if due_days is not None and due_days <= 4:
        nudge('B1', submit=-0.04 if phase in {'S5', 'S6', 'S8', 'S10'} else 0.03, rework=0.02, stop=0.02, note=f'Deadline pressure is high with only {round(due_days, 1)} days remaining.')
    elif due_days is not None and due_days > 14:
        adjusted['submit_on_time'] += 0.02
        adjusted['pause_or_stop'] -= 0.02

    return _normalize_probabilities(adjusted), notes, active_codes


def _scenario_confidence(overall_confidence: float, probability: float) -> float:
    return round(max(0.25, min(0.95, overall_confidence - abs(0.5 - probability) * 0.12)), 2)


def _action(
    *,
    code: str,
    title: str,
    priority: str,
    rationale: str,
    expected_impact: str,
    confidence: float,
    drivers: list[str],
) -> ForecastDecisionActionData:
    return ForecastDecisionActionData(
        code=code,
        title=title,
        priority=priority,
        rationale=rationale,
        expected_impact=expected_impact,
        confidence=round(max(0.3, min(0.95, confidence)), 2),
        drivers=drivers[:4],
    )


def _build_next_best_actions(
    *,
    phase: str,
    probabilities: dict[str, float],
    driver_scores: dict[str, float],
    overall_confidence: float,
    due_days: float | None,
    projected_path: list[str],
) -> list[ForecastDecisionActionData]:
    actions: list[ForecastDecisionActionData] = []

    def append_once(action: ForecastDecisionActionData) -> None:
        if any(existing.code == action.code for existing in actions):
            return
        actions.append(action)

    leading = max(probabilities.items(), key=lambda item: item[1])[0]
    projected_path_label = ' -> '.join(projected_path[:4]) if projected_path else _phase_label(phase)
    if leading == 'pause_or_stop':
        append_once(
            _action(
                code='decide_viability_now',
                title='Escalate viability decision',
                priority='now',
                rationale='The current trajectory is leaning toward pause or stop, so the tender needs an explicit viability decision.',
                expected_impact='Reduce avoidable churn and decide whether to recover, re-scope or stop.',
                confidence=overall_confidence + 0.06,
                drivers=[f'Pause/stop probability is {probabilities[leading]:.2f}.', f'Current phase is {_phase_label(phase)}.'],
            )
        )
    elif leading == 'extended_rework':
        append_once(
            _action(
                code='compress_review_loop',
                title='Compress review and rework loop',
                priority='now',
                rationale='The journey is most likely to stay trapped in rework unless blockers are actively reduced.',
                expected_impact='Shift probability mass from extended rework toward the submission corridor.',
                confidence=overall_confidence + 0.04,
                drivers=[f'Extended rework probability is {probabilities[leading]:.2f}.', f'Projected path: {projected_path_label}.'],
            )
        )
    else:
        append_once(
            _action(
                code='protect_submission_corridor',
                title='Protect the submission corridor',
                priority='now',
                rationale='The tender is leaning toward the submission path, so the main job is to avoid re-opening major blockers.',
                expected_impact='Keep the tender on the most direct path toward S9/S10.',
                confidence=overall_confidence + 0.03,
                drivers=[f'Submit-on-time probability is {probabilities[leading]:.2f}.', f'Projected path: {projected_path_label}.'],
            )
        )

    a1 = driver_scores.get('A1')
    if a1 is not None and a1 < 70:
        append_once(
            _action(
                code='close_requirement_gaps',
                title='Close requirement coverage gaps',
                priority='now',
                rationale='Incomplete coverage is still visible in the mirrored quality picture and will keep the tender in review pressure.',
                expected_impact='Raise A1 and reduce rework before the next gate.',
                confidence=overall_confidence + 0.05,
                drivers=[f'A1 is {a1:.1f}.', 'Requirement coverage gaps remain open.'],
            )
        )

    a4 = driver_scores.get('A4')
    if a4 is not None and (a4 < 75 or phase in {'S8', 'S10'}):
        append_once(
            _action(
                code='harden_compliance_closure',
                title='Harden compliance closure',
                priority='now' if phase in {'S8', 'S10'} else 'next',
                rationale='Compliance risk is still a material driver of the journey and should be closed before it re-routes the tender.',
                expected_impact='Reduce pause/stop pressure and protect submission or clarification closure.',
                confidence=overall_confidence + 0.04,
                drivers=[f'A4 is {a4:.1f}.', f'Current phase is {_phase_label(phase)}.'],
            )
        )

    b1 = driver_scores.get('B1')
    if (b1 is not None and b1 < 70) or (due_days is not None and due_days <= 5):
        append_once(
            _action(
                code='protect_deadline_window',
                title='Protect the deadline window',
                priority='now',
                rationale='Calendar pressure is becoming a first-order driver and needs explicit protection.',
                expected_impact='Prevent avoidable slippage into stop or late rework.',
                confidence=overall_confidence + 0.02,
                drivers=[f'B1 is {b1:.1f}.' if b1 is not None else 'B1 is not available.', f'Deadline buffer is {round(due_days or 0.0, 1)} days.'],
            )
        )

    b2 = driver_scores.get('B2')
    b4 = driver_scores.get('B4')
    if (b2 is not None and b2 < 70) or (b4 is not None and b4 < 70) or phase in {'S5', 'S6'}:
        append_once(
            _action(
                code='stabilize_contribution_loop',
                title='Stabilize contribution loop',
                priority='next',
                rationale='Responsiveness and contribution stability are still strong drivers of churn in the operational loop.',
                expected_impact='Reduce repeated reopenings between review and rework.',
                confidence=overall_confidence,
                drivers=[f'B2 is {b2:.1f}.' if b2 is not None else 'B2 is not available.', f'B4 is {b4:.1f}.' if b4 is not None else 'B4 is not available.'],
            )
        )

    if phase in {'S1', 'S2', 'S3'}:
        append_once(
            _action(
                code='stabilize_planning_and_assignment',
                title='Stabilize planning and assignments',
                priority='next',
                rationale='Early lifecycle states need explicit planning discipline before the tender can move into the stable execution corridor.',
                expected_impact='Increase predictability from S1/S2/S3 into S4/S5.',
                confidence=overall_confidence - 0.02,
                drivers=[f'Current phase is {_phase_label(phase)}.', 'Early lifecycle orchestration is still active.'],
            )
        )

    if not actions:
        append_once(
            _action(
                code='monitor_journey_signal',
                title='Monitor the journey signal',
                priority='watch',
                rationale='The current signal is stable enough that monitoring is more useful than forcing a new intervention.',
                expected_impact='Preserve the current path and refresh when new events arrive.',
                confidence=overall_confidence - 0.04,
                drivers=[f'Current phase is {_phase_label(phase)}.'],
            )
        )

    return actions[:3]


def _terminal_snapshot(phase: str) -> ForecastSnapshot:
    scenario_name, description = _TERMINAL_SCENARIOS[phase]
    action = _action(
        code=scenario_name,
        title='Preserve terminal analytical trace',
        priority='watch',
        rationale=description,
        expected_impact='Keep the final analytical outcome available for retrospective and audit.',
        confidence=0.96,
        drivers=[f'Current analytical phase is {phase}.'],
    )
    return ForecastSnapshot(
        summary=description,
        overall_confidence=0.96,
        scenarios=[
            ForecastScenarioData(
                name=scenario_name,
                probability=1.0,
                description=description,
                confidence=0.96,
                drivers=[f'Current analytical phase is {phase}.'],
                recommended_action=_scenario_action(scenario_name),
            )
        ],
        next_best_actions=[action],
        analysis_metadata={
            **_rollout_metadata(),
            'forecast_engine_active': 'terminal_state',
            'forecast_engine_candidates': [FORECAST_MARKOV_ENGINE, FORECAST_HEURISTIC_ENGINE],
            'forecast_signal_type': 'locked',
            'markov_model_active': False,
            'markov_model_version': MARKOV_MODEL_VERSION,
            'markov_bundle_kind': MARKOV_BUNDLE_KIND,
            'markov_full_journey_enabled': settings.markov_rollout_enabled,
            'markov_backtest_version': MARKOV_BACKTEST_VERSION,
            'forecast_decision_bundle_version': FORECAST_DECISION_BUNDLE_VERSION,
            'forecast_primary_action_code': action.code,
            'forecast_primary_action_confidence': action.confidence,
            'heuristic_bundle_version': HEURISTIC_FORECAST_VERSION,
        },
    )


def _not_ready_snapshot() -> ForecastSnapshot:
    action = _action(
        code='synchronize_tender',
        title='Synchronize tender mirror',
        priority='now',
        rationale='Forecasting cannot start until the tender mirror is available inside the KPI engine.',
        expected_impact='Unlock analytical snapshot, transitions and forecast generation.',
        confidence=0.0,
        drivers=['Tender mirror missing.'],
    )
    return ForecastSnapshot(
        summary='Forecasting is blocked until the tender is synchronized.',
        overall_confidence=0.0,
        scenarios=[
            ForecastScenarioData(
                name='not_ready',
                probability=None,
                description='Forecasting cannot start because the tender mirror is not available.',
                confidence=0.0,
                drivers=['Tender mirror missing.'],
                recommended_action='Synchronize the tender before requesting forecast scenarios.',
            )
        ],
        next_best_actions=[action],
        analysis_metadata={
            **_rollout_metadata(),
            'forecast_engine_active': 'not_ready',
            'forecast_engine_candidates': [FORECAST_MARKOV_ENGINE, FORECAST_HEURISTIC_ENGINE],
            'forecast_signal_type': 'not_ready',
            'markov_model_active': False,
            'markov_model_version': MARKOV_MODEL_VERSION,
            'markov_bundle_kind': MARKOV_BUNDLE_KIND,
            'markov_full_journey_enabled': settings.markov_rollout_enabled,
            'markov_backtest_version': MARKOV_BACKTEST_VERSION,
            'forecast_decision_bundle_version': FORECAST_DECISION_BUNDLE_VERSION,
            'forecast_primary_action_code': action.code,
            'forecast_primary_action_confidence': action.confidence,
            'heuristic_bundle_version': HEURISTIC_FORECAST_VERSION,
        },
    )


def _base_forecast_metadata(
    markov_bundle: dict[str, Any],
    phase: str,
    fallback_reason: str | None,
    *,
    signal_type: str,
    projected_path: list[str],
    driver_scores: dict[str, float],
    primary_action: ForecastDecisionActionData | None,
) -> dict[str, Any]:
    backtest = markov_bundle.get('backtest') or {}
    return {
        **_rollout_metadata(),
        'forecast_engine_candidates': [FORECAST_MARKOV_ENGINE, FORECAST_HEURISTIC_ENGINE],
        'forecast_signal_type': signal_type,
        'forecast_fallback_reason': fallback_reason,
        'heuristic_bundle_version': HEURISTIC_FORECAST_VERSION,
        'markov_model_version': markov_bundle.get('version', MARKOV_MODEL_VERSION),
        'markov_bundle_kind': markov_bundle.get('bundle_kind', MARKOV_BUNDLE_KIND),
        'markov_full_journey_enabled': True,
        'markov_state_scope': list(markov_bundle.get('state_scope') or MARKOV_STATE_SCOPE),
        'markov_absorbing_states': list(markov_bundle.get('absorbing_states') or MARKOV_ABSORBING_STATES),
        'markov_transition_samples': int(markov_bundle.get('sample_count') or 0),
        'markov_dataset_tenders': int(markov_bundle.get('dataset_tenders') or 0),
        'markov_current_state_support': int((markov_bundle.get('raw_outgoing') or {}).get(phase, 0)),
        'markov_source_mix': {str(key): int(value) for key, value in (markov_bundle.get('source_mix') or {}).items()},
        'markov_coverage_ratio': markov_bundle.get('coverage_ratio'),
        'markov_projected_path': projected_path,
        'markov_backtest_version': backtest.get('version', MARKOV_BACKTEST_VERSION),
        'markov_backtest_sample_count': backtest.get('sample_count'),
        'markov_backtest_submission_accuracy': backtest.get('submission_accuracy'),
        'markov_backtest_calibration_gap': backtest.get('calibration_gap'),
        'forecast_driver_kpis': list(driver_scores.keys()),
        'forecast_driver_scores': {code: round(value, 1) for code, value in driver_scores.items()},
        'forecast_primary_action_code': None if primary_action is None else primary_action.code,
        'forecast_primary_action_confidence': None if primary_action is None else primary_action.confidence,
        'forecast_decision_bundle_version': FORECAST_DECISION_BUNDLE_VERSION,
    }

def _build_markov_forecast(
    *,
    tender: dict[str, Any],
    snapshot_record: dict[str, Any],
    phase: str,
    markov_bundle: dict[str, Any],
    history_items: list[dict[str, Any]],
    transition_snapshot: Any | None,
    now: datetime,
) -> ForecastSnapshot | None:
    sample_count = int(markov_bundle.get('sample_count') or 0)
    current_support = int((markov_bundle.get('raw_outgoing') or {}).get(phase, 0))
    matrix = markov_bundle.get('matrix') or {}

    if phase not in MARKOV_STATE_SCOPE:
        return None
    if sample_count < MARKOV_MIN_TOTAL_TRANSITIONS:
        return None
    if current_support < MARKOV_MIN_CURRENT_STATE_SUPPORT:
        return None
    if phase not in matrix and phase not in MARKOV_ABSORBING_STATES:
        return None

    submit_probabilities = markov_bundle.get('submit_probabilities') or _solve_hitting_probabilities(
        matrix,
        target_states=set(MARKOV_POSITIVE_STATES),
        blocker_states={'S13'},
    )
    stop_probabilities = _solve_hitting_probabilities(
        matrix,
        target_states={'S13'},
        blocker_states=set(MARKOV_POSITIVE_STATES),
    )

    probabilities = _normalize_probabilities(
        {
            'submit_on_time': submit_probabilities.get(phase, 0.0),
            'extended_rework': max(0.0, 1.0 - submit_probabilities.get(phase, 0.0) - stop_probabilities.get(phase, 0.0)),
            'pause_or_stop': stop_probabilities.get(phase, 0.0),
        }
    )

    driver_scores = _driver_scores(snapshot_record)
    due_days = _days_until(_parse_datetime(tender.get('due_at')), now)
    probabilities, driver_notes, driver_codes = _apply_kpi_adjustments(
        probabilities,
        driver_scores=driver_scores,
        phase=phase,
        due_days=due_days,
    )
    projected_path = _project_path(phase, matrix)
    coverage_ratio = float(markov_bundle.get('coverage_ratio') or 0.0)
    backtest = markov_bundle.get('backtest') or {}
    backtest_accuracy = float(backtest.get('submission_accuracy') or 0.0)
    calibration_gap = float(backtest.get('calibration_gap') or 0.0)
    reconstructed_samples = int((markov_bundle.get('source_mix') or {}).get('reconstructed', 0))
    reconstructed_ratio = reconstructed_samples / max(1, sample_count)
    scored_kpis = list((snapshot_record.get('analysis_metadata') or {}).get('scored_kpis') or [])

    overall_confidence = 0.44
    overall_confidence += min(sample_count, 36) * 0.008
    overall_confidence += min(current_support, 8) * 0.03
    overall_confidence += coverage_ratio * 0.14
    overall_confidence += backtest_accuracy * 0.16
    overall_confidence += min(len(scored_kpis), 8) * 0.01
    overall_confidence += min(len(history_items), 10) * 0.008
    overall_confidence -= calibration_gap * 0.10
    overall_confidence -= reconstructed_ratio * 0.08
    overall_confidence = round(max(0.46, min(0.94, overall_confidence)), 2)

    path_label = ' -> '.join(projected_path) if len(projected_path) > 1 else _phase_label(phase)
    base_drivers = [
        f'Markov full-lifecycle v1 uses {sample_count} empirical transition samples across {markov_bundle.get("dataset_tenders", 0)} tenders.',
        f'Current phase {phase} has {current_support} outgoing historical samples in the full-journey bundle.',
        _row_driver(phase, matrix.get(phase)),
        f'Projected path is {path_label}.',
    ]
    if driver_notes:
        base_drivers.extend(driver_notes[:3])
    else:
        base_drivers.extend(_driver_lines(driver_scores, due_days)[:2])
    if backtest.get('sample_count'):
        base_drivers.append(
            f'Backtest accuracy is {backtest.get("submission_accuracy"):.2f} over {backtest.get("sample_count")} state samples.'
        )
    if reconstructed_samples:
        base_drivers.append(f'Reconstructed history contributes {reconstructed_samples}/{sample_count} transition samples.')
    if transition_snapshot is not None and getattr(transition_snapshot, 'items', None):
        latest_item = transition_snapshot.items[0]
        base_drivers.append(f'Latest mirrored transition is {latest_item.from_state}->{latest_item.to_state}.')

    scenarios: list[ForecastScenarioData] = []
    for name in ['submit_on_time', 'extended_rework', 'pause_or_stop']:
        probability = probabilities[name]
        scenario_drivers = list(base_drivers[:4])
        if name == 'submit_on_time':
            scenario_drivers.append('This probability tracks whether the tender reaches S9/S10 before terminal stop conditions materialize.')
        elif name == 'extended_rework':
            scenario_drivers.append('This probability captures residual mass that keeps circulating in the review, rework and clarification loop.')
        else:
            scenario_drivers.append('This probability tracks whether S13 is reached before the submission corridor stabilizes.')
        if driver_codes:
            scenario_drivers.append(f'Primary KPI drivers are {", ".join(driver_codes[:4])}.')
        scenarios.append(
            ForecastScenarioData(
                name=name,
                probability=probability,
                description=_SCENARIO_DESCRIPTIONS[name],
                confidence=_scenario_confidence(overall_confidence, probability),
                drivers=scenario_drivers,
                recommended_action=_scenario_action(name),
            )
        )

    next_best_actions = _build_next_best_actions(
        phase=phase,
        probabilities=probabilities,
        driver_scores=driver_scores,
        overall_confidence=overall_confidence,
        due_days=due_days,
        projected_path=projected_path,
    )
    leading = max(scenarios, key=lambda item: item.probability or 0.0)
    primary_action = next_best_actions[0] if next_best_actions else None
    return ForecastSnapshot(
        summary=(
            f'Markov full-lifecycle v1 currently leans toward {leading.name.replace("_", " ")} '
            f'from {_phase_label(phase)} with empirical support N={current_support}.'
        ),
        overall_confidence=overall_confidence,
        scenarios=scenarios,
        next_best_actions=next_best_actions,
        analysis_metadata={
            **_base_forecast_metadata(
                markov_bundle,
                phase,
                None,
                signal_type='calibrated',
                projected_path=projected_path,
                driver_scores=driver_scores,
                primary_action=primary_action,
            ),
            'forecast_engine_active': FORECAST_MARKOV_ENGINE,
            'markov_model_active': True,
        },
    )


def _build_heuristic_forecast(
    *,
    tender: dict[str, Any],
    snapshot_record: dict[str, Any],
    transition_snapshot: Any | None,
    history_items: list[dict[str, Any]],
    events: list[dict[str, Any]],
    markov_bundle: dict[str, Any],
    fallback_reason: str | None,
    now: datetime,
) -> ForecastSnapshot:
    phase = str(snapshot_record.get('analytical_phase') or 'S2')
    health = _normalized(snapshot_record.get('health')) or 'unknown'
    metadata = snapshot_record.get('analysis_metadata') or {}
    history_count = len(history_items)
    scored_kpis = list(metadata.get('scored_kpis') or [])
    due_days = _days_until(_parse_datetime(tender.get('due_at')), now)
    q_score = _score_value(snapshot_record, 'Q')
    e_score = _score_value(snapshot_record, 'E')
    summary_drivers: list[str] = []
    probabilities = dict(_BASE_PROBABILITIES.get(phase, _BASE_PROBABILITIES['S4']))

    if health == 'green':
        probabilities['submit_on_time'] += 0.16
        probabilities['extended_rework'] -= 0.08
        probabilities['pause_or_stop'] -= 0.08
        summary_drivers.append('Current health is green, which supports the submission path.')
    elif health == 'amber':
        probabilities['extended_rework'] += 0.05
        probabilities['pause_or_stop'] -= 0.02
        summary_drivers.append('Current health is amber, so rework pressure remains material.')
    elif health == 'red':
        probabilities['submit_on_time'] -= 0.18
        probabilities['extended_rework'] += 0.08
        probabilities['pause_or_stop'] += 0.10
        summary_drivers.append('Current health is red, which raises the chance of rework or stop decisions.')

    if phase in {'S6', 'S8', 'S10'}:
        probabilities['submit_on_time'] -= 0.08
        probabilities['extended_rework'] += 0.12
        summary_drivers.append(f'Analytical phase {phase} reflects unresolved blockers that usually extend the workflow.')
    elif phase == 'S7':
        probabilities['submit_on_time'] += 0.08
        summary_drivers.append('The tender is already in integrated draft, which improves submission readiness.')

    if q_score is not None:
        if q_score >= 75:
            probabilities['submit_on_time'] += 0.07
            summary_drivers.append(f'Qualitative index Q is {q_score:.1f}, which supports a cleaner submission path.')
        elif q_score < 55:
            probabilities['submit_on_time'] -= 0.08
            probabilities['pause_or_stop'] += 0.06
            summary_drivers.append(f'Qualitative index Q is only {q_score:.1f}, which weakens offer readiness.')

    if e_score is not None:
        if e_score >= 75:
            probabilities['submit_on_time'] += 0.06
            summary_drivers.append(f'Operational efficiency E is {e_score:.1f}, so execution friction is limited.')
        elif e_score < 55:
            probabilities['extended_rework'] += 0.05
            probabilities['pause_or_stop'] += 0.04
            summary_drivers.append(f'Operational efficiency E is {e_score:.1f}, which increases execution risk.')

    if due_days is not None:
        if due_days <= 3:
            if health == 'green':
                probabilities['submit_on_time'] += 0.05
                summary_drivers.append(f'The deadline is in {round(due_days, 1)} days, so the team is likely to push to submit.')
            else:
                probabilities['submit_on_time'] -= 0.10
                probabilities['extended_rework'] += 0.05
                probabilities['pause_or_stop'] += 0.05
                summary_drivers.append(f'The deadline is in {round(due_days, 1)} days while blockers remain active.')
        elif due_days <= 7:
            probabilities['extended_rework'] += 0.03
            summary_drivers.append(f'The deadline is in {round(due_days, 1)} days, keeping pressure on the rework path.')
        elif due_days > 21:
            probabilities['pause_or_stop'] -= 0.03
            probabilities['submit_on_time'] += 0.03
            summary_drivers.append('There is still enough calendar buffer to recover before submission.')
    else:
        summary_drivers.append('Tender deadline is missing, so the forecast remains less certain than usual.')

    if transition_snapshot is not None and getattr(transition_snapshot, 'items', None):
        latest_item = transition_snapshot.items[0]
        if latest_item.to_state in {'S6', 'S8', 'S10'}:
            probabilities['extended_rework'] += 0.06
            summary_drivers.append(f'Latest mirrored transition points to {latest_item.to_state}.')

    driver_scores = _driver_scores(snapshot_record)
    probabilities, driver_notes, driver_codes = _apply_kpi_adjustments(
        probabilities,
        driver_scores=driver_scores,
        phase=phase,
        due_days=due_days,
    )
    projected_path = _project_path(phase, markov_bundle.get('matrix') or {}) if phase in MARKOV_STATE_SCOPE else [phase]
    summary_drivers.extend(driver_notes[:3])

    backtest = markov_bundle.get('backtest') or {}
    backtest_accuracy = float(backtest.get('submission_accuracy') or 0.0)
    overall_confidence = 0.50
    overall_confidence += min(len(scored_kpis), 8) * 0.03
    overall_confidence += min(history_count, 6) * 0.02
    overall_confidence += min(len(events), 20) * 0.005
    overall_confidence += backtest_accuracy * 0.05
    if metadata.get('reconstructed'):
        overall_confidence -= 0.06
    overall_confidence = round(max(0.35, min(0.90, overall_confidence)), 2)

    scenarios: list[ForecastScenarioData] = []
    for name in ['submit_on_time', 'extended_rework', 'pause_or_stop']:
        scenario_probability = probabilities[name]
        scenario_confidence = _scenario_confidence(overall_confidence, scenario_probability)
        scenario_drivers = list(summary_drivers[:4])
        if name == 'submit_on_time':
            scenario_drivers.append('Submission probability increases when Q/E remain stable and blockers do not re-open.')
        elif name == 'extended_rework':
            scenario_drivers.append('Review, rework and gate pressure are the strongest predictors of this scenario.')
        else:
            scenario_drivers.append('This scenario grows when deadline pressure and poor health stay unresolved.')
        if driver_codes:
            scenario_drivers.append(f'Primary KPI drivers are {", ".join(driver_codes[:4])}.')
        scenarios.append(
            ForecastScenarioData(
                name=name,
                probability=scenario_probability,
                description=_SCENARIO_DESCRIPTIONS[name],
                confidence=scenario_confidence,
                drivers=scenario_drivers,
                recommended_action=_scenario_action(name),
            )
        )

    next_best_actions = _build_next_best_actions(
        phase=phase,
        probabilities=probabilities,
        driver_scores=driver_scores,
        overall_confidence=overall_confidence,
        due_days=due_days,
        projected_path=projected_path,
    )
    leading = max(scenarios, key=lambda item: item.probability or 0.0)
    primary_action = next_best_actions[0] if next_best_actions else None
    return ForecastSnapshot(
        summary=f'Forecast currently leans toward {leading.name.replace("_", " ")} from {_phase_label(phase)} with {health} health.',
        overall_confidence=overall_confidence,
        scenarios=scenarios,
        next_best_actions=next_best_actions,
        analysis_metadata={
            **_base_forecast_metadata(
                markov_bundle,
                phase,
                fallback_reason,
                signal_type='predicted',
                projected_path=projected_path,
                driver_scores=driver_scores,
                primary_action=primary_action,
            ),
            'forecast_engine_active': FORECAST_HEURISTIC_ENGINE,
            'markov_model_active': False,
        },
    )


def build_forecast_snapshot(
    *,
    tender: dict[str, Any] | None,
    snapshot_record: dict[str, Any] | None,
    transition_snapshot: Any | None,
    history_items: list[dict[str, Any]],
    events: list[dict[str, Any]],
    markov_history_points: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> ForecastSnapshot:
    now = now or datetime.now(timezone.utc)
    if tender is None or snapshot_record is None:
        return _not_ready_snapshot()

    phase = str(snapshot_record.get('analytical_phase') or 'S2')
    if phase in _TERMINAL_SCENARIOS:
        return _terminal_snapshot(phase)

    markov_bundle = _build_markov_bundle(list(markov_history_points or []))
    fallback_reason: str | None = None

    if settings.markov_rollout_enabled and phase in MARKOV_STATE_SCOPE:
        markov_forecast = _build_markov_forecast(
            tender=tender,
            snapshot_record=snapshot_record,
            phase=phase,
            markov_bundle=markov_bundle,
            history_items=history_items,
            transition_snapshot=transition_snapshot,
            now=now,
        )
        if markov_forecast is not None:
            return markov_forecast

        sample_count = int(markov_bundle.get('sample_count') or 0)
        current_support = int((markov_bundle.get('raw_outgoing') or {}).get(phase, 0))
        if sample_count < MARKOV_MIN_TOTAL_TRANSITIONS:
            fallback_reason = 'markov_dataset_insufficient'
        elif current_support < MARKOV_MIN_CURRENT_STATE_SUPPORT:
            fallback_reason = 'current_state_support_insufficient'
        else:
            fallback_reason = 'markov_row_unavailable'
    elif not settings.markov_rollout_enabled:
        fallback_reason = 'markov_rollout_disabled'
    else:
        fallback_reason = 'phase_out_of_scope'

    return _build_heuristic_forecast(
        tender=tender,
        snapshot_record=snapshot_record,
        transition_snapshot=transition_snapshot,
        history_items=history_items,
        events=events,
        markov_bundle=markov_bundle,
        fallback_reason=fallback_reason,
        now=now,
    )
