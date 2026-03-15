from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class ForecastScenarioData:
    name: str
    probability: float | None
    description: str | None
    confidence: float | None
    drivers: list[str]
    recommended_action: str | None


@dataclass(slots=True)
class ForecastSnapshot:
    summary: str
    overall_confidence: float | None
    scenarios: list[ForecastScenarioData]


_TERMINAL_SCENARIOS = {
    'S11': ('win_locked', 'Tender outcome is already recorded as win.'),
    'S12': ('loss_locked', 'Tender outcome is already recorded as loss.'),
    'S13': ('stop_locked', 'Tender is already excluded, withdrawn or marked as no-bid.'),
}
_BASE_PROBABILITIES = {
    'S0': {'submit_on_time': 0.10, 'extended_rework': 0.35, 'pause_or_stop': 0.55},
    'S2': {'submit_on_time': 0.18, 'extended_rework': 0.42, 'pause_or_stop': 0.40},
    'S3': {'submit_on_time': 0.32, 'extended_rework': 0.48, 'pause_or_stop': 0.20},
    'S4': {'submit_on_time': 0.42, 'extended_rework': 0.40, 'pause_or_stop': 0.18},
    'S5': {'submit_on_time': 0.34, 'extended_rework': 0.51, 'pause_or_stop': 0.15},
    'S6': {'submit_on_time': 0.24, 'extended_rework': 0.58, 'pause_or_stop': 0.18},
    'S7': {'submit_on_time': 0.62, 'extended_rework': 0.26, 'pause_or_stop': 0.12},
    'S8': {'submit_on_time': 0.46, 'extended_rework': 0.40, 'pause_or_stop': 0.14},
    'S9': {'submit_on_time': 0.78, 'extended_rework': 0.14, 'pause_or_stop': 0.08},
    'S10': {'submit_on_time': 0.68, 'extended_rework': 0.20, 'pause_or_stop': 0.12},
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
    cleaned = {key: max(0.01, value) for key, value in values.items()}
    total = sum(cleaned.values())
    normalized = {key: round(value / total, 3) for key, value in cleaned.items()}
    delta = round(1.0 - sum(normalized.values()), 3)
    first_key = next(iter(normalized))
    normalized[first_key] = round(normalized[first_key] + delta, 3)
    return normalized


def _scenario_action(name: str) -> str:
    if name == 'submit_on_time':
        return 'Protect the current submission path and keep high-risk blockers from re-opening.'
    if name == 'extended_rework':
        return 'Prioritize blocker closure and compress the review loop before the next gate.'
    if name == 'pause_or_stop':
        return 'Escalate viability immediately and decide whether to re-scope or stop the tender.'
    if name == 'win_locked':
        return 'Shift to post-award mobilization and preserve the analytical trace for audit.'
    if name == 'loss_locked':
        return 'Archive the loss drivers and feed them into retrospective learning.'
    return 'Keep monitoring the tender trajectory and update the latest analytical snapshot when new events arrive.'


def build_forecast_snapshot(
    *,
    tender: dict[str, Any] | None,
    snapshot_record: dict[str, Any] | None,
    transition_snapshot: Any | None,
    history_items: list[dict[str, Any]],
    events: list[dict[str, Any]],
    now: datetime | None = None,
) -> ForecastSnapshot:
    now = now or datetime.now(timezone.utc)
    if tender is None or snapshot_record is None:
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
        )

    phase = str(snapshot_record.get('analytical_phase') or 'S2')
    health = _normalized(snapshot_record.get('health')) or 'unknown'
    metadata = snapshot_record.get('analysis_metadata') or {}
    history_count = len(history_items)
    scored_kpis = list(metadata.get('scored_kpis') or [])
    due_days = _days_until(_parse_datetime(tender.get('due_at')), now)
    q_score = _score_value(snapshot_record, 'Q')
    e_score = _score_value(snapshot_record, 'E')
    summary_drivers: list[str] = []

    if phase in _TERMINAL_SCENARIOS:
        scenario_name, description = _TERMINAL_SCENARIOS[phase]
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
        )

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

    if phase in {'S6', 'S8'}:
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
        if latest_item.to_state in {'S6', 'S8'}:
            probabilities['extended_rework'] += 0.06
            summary_drivers.append(f'Latest mirrored transition points to {latest_item.to_state}.')

    probabilities = _normalize_probabilities(probabilities)

    overall_confidence = 0.52
    overall_confidence += min(len(scored_kpis), 8) * 0.03
    overall_confidence += min(history_count, 6) * 0.02
    overall_confidence += min(len(events), 20) * 0.005
    if metadata.get('reconstructed'):
        overall_confidence -= 0.06
    overall_confidence = round(max(0.35, min(0.92, overall_confidence)), 2)

    scenario_descriptions = {
        'submit_on_time': 'The tender is likely to stay on the delivery path and reach submission without major detours.',
        'extended_rework': 'The tender is likely to loop through additional review, clarification or compliance work before it can progress.',
        'pause_or_stop': 'The tender may be paused, de-scoped or stopped if the current risk picture does not improve.',
    }

    scenarios: list[ForecastScenarioData] = []
    for name in ['submit_on_time', 'extended_rework', 'pause_or_stop']:
        scenario_probability = probabilities[name]
        scenario_confidence = round(max(0.25, min(0.95, overall_confidence - abs(0.5 - scenario_probability) * 0.12)), 2)
        scenario_drivers = list(summary_drivers[:4])
        if name == 'submit_on_time':
            scenario_drivers.append('Submission probability increases when Q/E remain stable and blockers do not re-open.')
        elif name == 'extended_rework':
            scenario_drivers.append('Review, rework and gate pressure are the strongest predictors of this scenario.')
        else:
            scenario_drivers.append('This scenario grows when deadline pressure and poor health stay unresolved.')
        scenarios.append(
            ForecastScenarioData(
                name=name,
                probability=scenario_probability,
                description=scenario_descriptions[name],
                confidence=scenario_confidence,
                drivers=scenario_drivers,
                recommended_action=_scenario_action(name),
            )
        )

    leading = max(scenarios, key=lambda item: item.probability or 0.0)
    summary = f"Forecast currently leans toward {leading.name.replace('_', ' ')} from phase {phase} with {health} health."
    return ForecastSnapshot(summary=summary, overall_confidence=overall_confidence, scenarios=scenarios)
