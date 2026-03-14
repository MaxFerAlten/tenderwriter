"""Deterministic analytical scoring helpers for the KPI reason engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.schemas import HealthClass, KpiScore

_ACTIVE_SECTION_STATUSES = {"in_progress", "in_review", "approved", "submitted"}
_COMPLETED_SECTION_STATUSES = {"approved", "submitted"}
_ADDRESSED_REQUIREMENT_STATUSES = {"partially_addressed", "fully_addressed"}
_TERMINAL_PHASES = {
    "won": "S11",
    "win": "S11",
    "lost": "S12",
    "loss": "S12",
    "cancelled": "S13",
    "canceled": "S13",
    "excluded": "S13",
    "withdrawn": "S13",
    "no-bid": "S13",
    "no_bid": "S13",
}
_OPERATIONAL_WEIGHTS = {"B1": 0.30, "B2": 0.30, "B3": 0.15, "B4": 0.25}


@dataclass(slots=True)
class AnalysisSnapshot:
    analytical_phase: str | None
    health: HealthClass
    kpis: list[KpiScore]
    notes: list[str]
    summary: str


@dataclass(slots=True)
class OperationalState:
    requests: list[dict[str, Any]]
    reviews_started: int
    reviews_completed: int
    reworks: list[dict[str, Any]]
    gates: list[dict[str, Any]]
    calls: list[dict[str, Any]]
    unique_contribution_ids: set[str]


@dataclass(slots=True)
class OperationalSnapshot:
    b1: KpiScore
    b2: KpiScore
    b3: KpiScore
    b4: KpiScore
    e: KpiScore
    notes: list[str]
    summary: str


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def _health_from_score(value: float | None, *, green: float, amber: float) -> HealthClass:
    if value is None:
        return "unknown"
    if value >= green:
        return "green"
    if value >= amber:
        return "amber"
    return "red"


def _count_events(events: list[dict[str, Any]], event_type: str) -> int:
    target = _normalized(event_type)
    return sum(1 for event in events if _normalized(event.get("event_type")) == target)


def _latest_outcome(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if _normalized(event.get("event_type")) != "tender_outcome_recorded":
            continue
        payload = _event_payload(event)
        outcome = _normalized(payload.get("outcome"))
        if outcome:
            return outcome
    return None


def _days_until(due_at: datetime | None, now: datetime) -> float | None:
    if due_at is None:
        return None
    return (due_at - now).total_seconds() / 86400


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 3600, 2)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
        return payload["payload"]
    return payload if isinstance(payload, dict) else {}


def _score_a1(
    requirement_count: int,
    addressed_requirements: int,
    section_count: int,
    active_sections: int,
    proposal_updates: int,
    requirements_extracted: bool,
) -> KpiScore:
    evidence: list[str] = []
    if requirement_count == 0:
        if not requirements_extracted:
            return KpiScore(
                kpi_code="A1",
                label="Requirement coverage is waiting for extracted requirements.",
                provenance="unknown",
                health="unknown",
                confidence=0.0,
                evidence=["No `requirements_extracted` event was observed yet."],
            )

        return KpiScore(
            kpi_code="A1",
            value=0.0,
            label="No tender requirements were extracted from the uploaded document.",
            provenance="inferred",
            health="red",
            confidence=0.55,
            evidence=["The tender document was processed but yielded zero persisted requirements."],
        )

    coverage_ratio = addressed_requirements / requirement_count
    section_capacity_ratio = min(section_count / requirement_count, 1.0)
    section_progress_ratio = active_sections / section_count if section_count else 0.0
    update_ratio = min(proposal_updates / requirement_count, 1.0)
    value = round(
        (
            (coverage_ratio * 0.55)
            + (section_capacity_ratio * 0.20)
            + (section_progress_ratio * 0.15)
            + (update_ratio * 0.10)
        )
        * 100,
        1,
    )

    evidence.append(f"Requirements tracked: {requirement_count}.")
    evidence.append(f"Requirements already linked or addressed: {addressed_requirements}.")
    evidence.append(f"Proposal sections available: {section_count}, active sections: {active_sections}.")
    evidence.append(f"Proposal section update events observed: {proposal_updates}.")

    provenance = "measured" if addressed_requirements > 0 else "inferred"
    confidence = 0.82 if addressed_requirements > 0 else round(min(0.78, 0.58 + (section_count * 0.04)), 2)
    return KpiScore(
        kpi_code="A1",
        value=value,
        label="Requirement coverage proxy built from persisted requirements and proposal progress.",
        provenance=provenance,
        health=_health_from_score(value, green=75.0, amber=45.0),
        confidence=confidence,
        evidence=evidence,
    )


def _score_a4(
    *,
    document_ingested: bool,
    requirement_count: int,
    addressed_requirements: int,
    high_priority_requirements: int,
    section_count: int,
    active_sections: int,
    due_at: datetime | None,
    submitted: bool,
    now: datetime,
) -> KpiScore:
    if not document_ingested:
        return KpiScore(
            kpi_code="A4",
            label="Compliance readiness becomes available after tender document ingestion.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No `tender_document_ingested` event was observed yet."],
        )

    if requirement_count == 0:
        return KpiScore(
            kpi_code="A4",
            value=0.0,
            label="Compliance readiness is blocked because no requirements are available.",
            provenance="inferred",
            health="red",
            confidence=0.58,
            evidence=["The tender cannot establish compliance readiness without extracted requirements."],
        )

    coverage_ratio = addressed_requirements / requirement_count
    unresolved_ratio = 1.0 - coverage_ratio
    high_priority_ratio = high_priority_requirements / requirement_count
    section_progress_ratio = active_sections / section_count if section_count else 0.0
    due_days = _days_until(due_at, now)

    if due_days is None:
        due_risk = 0.35
        due_evidence = "Tender deadline is missing from the synchronized mirror."
    elif due_days < 0:
        due_risk = 1.0
        due_evidence = f"Tender deadline already passed {abs(round(due_days, 1))} days ago."
    elif due_days <= 3:
        due_risk = 0.90
        due_evidence = f"Tender deadline is in {round(due_days, 1)} days."
    elif due_days <= 7:
        due_risk = 0.75
        due_evidence = f"Tender deadline is in {round(due_days, 1)} days."
    elif due_days <= 14:
        due_risk = 0.50
        due_evidence = f"Tender deadline is in {round(due_days, 1)} days."
    else:
        due_risk = 0.20
        due_evidence = f"Tender deadline is in {round(due_days, 1)} days."

    missing_section_penalty = 0.10 if section_count == 0 else 0.0
    progress_offset = (1.0 - section_progress_ratio) * 0.10
    risk = min(
        1.0,
        (unresolved_ratio * 0.45)
        + (due_risk * 0.35)
        + (high_priority_ratio * 0.10)
        + missing_section_penalty
        + progress_offset,
    )
    if submitted:
        risk = max(0.0, risk - 0.10)

    value = round((1.0 - risk) * 100, 1)
    evidence = [
        f"Tracked requirements: {requirement_count}, high-priority requirements: {high_priority_requirements}.",
        f"Requirements already linked or addressed: {addressed_requirements}.",
        f"Proposal sections available: {section_count}, active sections: {active_sections}.",
        due_evidence,
    ]

    confidence = 0.78 if due_at and requirement_count > 0 else 0.64
    return KpiScore(
        kpi_code="A4",
        value=value,
        label="Compliance readiness proxy combining requirement backlog, proposal progress and deadline pressure.",
        provenance="inferred",
        health=_health_from_score(value, green=75.0, amber=45.0),
        confidence=confidence,
        evidence=evidence,
    )

def _collect_operational_state(events: list[dict[str, Any]]) -> OperationalState:
    requests: dict[str, dict[str, Any]] = {}
    reworks: dict[str, dict[str, Any]] = {}
    gates: dict[str, dict[str, Any]] = {}
    calls: dict[str, dict[str, Any]] = {}
    unique_contribution_ids: set[str] = set()
    reviews_started = 0
    reviews_completed = 0

    for index, event in enumerate(events, start=1):
        event_type = _normalized(event.get("event_type"))
        payload = _event_payload(event)
        occurred_at = _parse_datetime(event.get("occurred_at"))

        if event_type == "contribution_request_created":
            request_id = str(payload.get("external_request_id") or f"request-{index}")
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            requests[request_id] = {
                "request_id": request_id,
                "contribution_id": contribution_id,
                "requested_at": _parse_datetime(payload.get("requested_at")) or occurred_at,
                "due_at": _parse_datetime(payload.get("due_at")),
                "sla_target_hours": _coerce_float(payload.get("sla_target_hours")),
                "sla_max_hours": _coerce_float(payload.get("sla_max_hours")),
                "received_at": None,
                "lateness_hours": None,
                "response_time_hours": None,
            }
            continue

        if event_type == "contribution_due_date_set":
            request_id = str(payload.get("external_request_id") or "")
            if request_id:
                requests.setdefault(request_id, {"request_id": request_id, "contribution_id": str(payload.get("external_contribution_id") or "")})
                requests[request_id]["due_at"] = _parse_datetime(payload.get("due_at"))
            continue

        if event_type == "contribution_received":
            request_id = str(payload.get("external_request_id") or f"received-{index}")
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            current = requests.setdefault(
                request_id,
                {
                    "request_id": request_id,
                    "contribution_id": contribution_id,
                    "requested_at": _parse_datetime(payload.get("requested_at")),
                    "due_at": _parse_datetime(payload.get("due_at")),
                    "sla_target_hours": None,
                    "sla_max_hours": None,
                },
            )
            current["received_at"] = _parse_datetime(payload.get("received_at")) or occurred_at
            current["requested_at"] = current.get("requested_at") or _parse_datetime(payload.get("requested_at"))
            current["due_at"] = current.get("due_at") or _parse_datetime(payload.get("due_at"))
            current["response_time_hours"] = _coerce_float(payload.get("response_time_hours"))
            current["lateness_hours"] = _coerce_float(payload.get("lateness_hours"))
            continue

        if event_type == "review_cycle_started":
            reviews_started += 1
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            continue

        if event_type == "contribution_review_completed":
            reviews_completed += 1
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            continue

        if event_type == "rework_requested":
            rework_id = str(payload.get("external_rework_id") or f"rework-{index}")
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            reworks[rework_id] = {
                "rework_id": rework_id,
                "contribution_id": contribution_id,
                "requested_at": _parse_datetime(payload.get("requested_at")) or occurred_at,
                "resolved_at": None,
                "is_blocking": bool(payload.get("is_blocking", False)),
                "severity": _normalized(payload.get("severity")) or "medium",
            }
            continue

        if event_type == "rework_resolved":
            rework_id = str(payload.get("external_rework_id") or f"rework-resolved-{index}")
            current = reworks.setdefault(
                rework_id,
                {
                    "rework_id": rework_id,
                    "contribution_id": str(payload.get("external_contribution_id") or ""),
                    "requested_at": _parse_datetime(payload.get("requested_at")),
                    "is_blocking": bool(payload.get("is_blocking", False)),
                    "severity": _normalized(payload.get("severity")) or "medium",
                },
            )
            current["resolved_at"] = _parse_datetime(payload.get("resolved_at")) or occurred_at
            continue

        if event_type == "compliance_gate_opened":
            gate_id = str(payload.get("external_gate_id") or f"gate-{index}")
            gates[gate_id] = {
                "gate_id": gate_id,
                "status": "open",
                "gate_name": payload.get("gate_name"),
            }
            continue

        if event_type in {"compliance_gate_passed", "compliance_gate_failed"}:
            gate_id = str(payload.get("external_gate_id") or f"gate-{index}")
            gates.setdefault(gate_id, {"gate_id": gate_id, "gate_name": payload.get("gate_name")})
            gates[gate_id]["status"] = "passed" if event_type.endswith("passed") else "failed"
            continue

        if event_type == "call_scheduled":
            call_id = str(payload.get("external_call_session_id") or f"call-{index}")
            calls[call_id] = {
                "call_id": call_id,
                "scheduled_at": _parse_datetime(payload.get("scheduled_at")) or occurred_at,
                "attendance": {},
            }
            continue

        if event_type == "call_attendance_recorded":
            call_id = str(payload.get("external_call_session_id") or f"call-{index}")
            call = calls.setdefault(call_id, {"call_id": call_id, "scheduled_at": _parse_datetime(payload.get("scheduled_at")), "attendance": {}})
            attendee_key = str(payload.get("user_id") or payload.get("attendee_label") or payload.get("attendance_record_id") or f"attendee-{index}")
            call["attendance"][attendee_key] = _normalized(payload.get("attendance_status")) or "invited"

    return OperationalState(
        requests=list(requests.values()),
        reviews_started=reviews_started,
        reviews_completed=reviews_completed,
        reworks=list(reworks.values()),
        gates=list(gates.values()),
        calls=list(calls.values()),
        unique_contribution_ids=unique_contribution_ids,
    )


def _score_b1(requests: list[dict[str, Any]], now: datetime) -> KpiScore:
    if not requests:
        return KpiScore(
            kpi_code="B1",
            label="Deadline adherence becomes available after at least one tracked contribution request.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No `contribution_request_created` events were observed yet."],
        )

    scores: list[float] = []
    on_time = 0
    late = 0
    overdue_open = 0
    for request in requests:
        due_at = request.get("due_at")
        received_at = request.get("received_at")
        if received_at is not None:
            if due_at is None or received_at <= due_at:
                scores.append(100.0)
                on_time += 1
            else:
                late += 1
                lateness_hours = request.get("lateness_hours")
                if lateness_hours is None:
                    lateness_hours = max(0.0, (received_at - due_at).total_seconds() / 3600)
                if lateness_hours <= 24:
                    scores.append(70.0)
                elif lateness_hours <= 72:
                    scores.append(40.0)
                else:
                    scores.append(10.0)
            continue

        if due_at is not None and now > due_at:
            overdue_open += 1
            overdue_hours = max(0.0, (now - due_at).total_seconds() / 3600)
            if overdue_hours <= 24:
                scores.append(35.0)
            elif overdue_hours <= 72:
                scores.append(15.0)
            else:
                scores.append(0.0)
            continue

        scores.append(75.0)

    value = round(sum(scores) / len(scores), 1)
    return KpiScore(
        kpi_code="B1",
        value=value,
        label="Deadline adherence across tracked contribution requests.",
        provenance="measured",
        health=_health_from_score(value, green=80.0, amber=55.0),
        confidence=0.88,
        evidence=[
            f"Tracked contribution requests: {len(requests)}.",
            f"On-time deliveries: {on_time}, late deliveries: {late}, overdue open requests: {overdue_open}.",
        ],
    )


def _score_b2(requests: list[dict[str, Any]], now: datetime) -> KpiScore:
    eligible = [request for request in requests if request.get("requested_at") is not None]
    if not eligible:
        return KpiScore(
            kpi_code="B2",
            label="Operational responsiveness becomes available after requests are tracked with timestamps.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No request/response cycle with timestamps was observed yet."],
        )
    scores: list[float] = []
    within_target = 0
    within_max = 0
    breached = 0
    for request in eligible:
        requested_at = request.get("requested_at")
        received_at = request.get("received_at") or now
        response_time = request.get("response_time_hours")
        if response_time is None:
            response_time = _hours_between(requested_at, received_at)
        if response_time is None:
            continue

        target = request.get("sla_target_hours")
        max_hours = request.get("sla_max_hours")
        if target is None and max_hours is None:
            target = 8.0
            max_hours = 24.0
        elif target is None:
            target = max_hours
        elif max_hours is None:
            max_hours = max(target * 2.0, target)
        else:
            max_hours = max(max_hours, target)

        if request.get("received_at") is not None:
            if response_time <= target:
                scores.append(100.0)
                within_target += 1
            elif response_time <= max_hours:
                scores.append(60.0)
                within_max += 1
            else:
                scores.append(15.0)
                breached += 1
            continue

        if response_time <= target:
            scores.append(70.0)
        elif response_time <= max_hours:
            scores.append(40.0)
        else:
            scores.append(5.0)
            breached += 1

    if not scores:
        return KpiScore(
            kpi_code="B2",
            label="Operational responsiveness has no scoreable request cycle yet.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["Tracked requests were missing sufficient timing data."],
        )

    value = round(sum(scores) / len(scores), 1)
    return KpiScore(
        kpi_code="B2",
        value=value,
        label="Operational responsiveness against SLA target and maximum thresholds.",
        provenance="measured",
        health=_health_from_score(value, green=80.0, amber=55.0),
        confidence=0.86,
        evidence=[
            f"Requests scored for responsiveness: {len(scores)}.",
            f"Within SLA target: {within_target}, within SLA max: {within_max}, breached: {breached}.",
        ],
    )


def _score_b3(calls: list[dict[str, Any]], now: datetime) -> KpiScore:
    attendance_calls = [call for call in calls if call.get("attendance")]
    if not attendance_calls:
        return KpiScore(
            kpi_code="B3",
            label="Call participation becomes available after attendance is recorded.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No `call_attendance_recorded` events were observed yet."],
        )

    scores: list[float] = []
    total_attended = 0
    total_expected = 0
    for call in attendance_calls:
        statuses = list((call.get("attendance") or {}).values())
        attended = sum(1 for status in statuses if status == "attended")
        expected = sum(1 for status in statuses if status in {"attended", "absent", "invited"})
        if expected == 0:
            if call.get("scheduled_at") and call["scheduled_at"] <= now:
                scores.append(30.0)
            else:
                scores.append(70.0)
            continue
        total_attended += attended
        total_expected += expected
        scores.append(round((attended / expected) * 100, 1))

    value = round(sum(scores) / len(scores), 1)
    return KpiScore(
        kpi_code="B3",
        value=value,
        label="Participation rate across scheduled tender calls with recorded attendance.",
        provenance="measured",
        health=_health_from_score(value, green=80.0, amber=55.0),
        confidence=0.84,
        evidence=[
            f"Calls with attendance records: {len(attendance_calls)}.",
            f"Recorded participants attended: {total_attended}/{total_expected or 0}.",
        ],
    )


def _score_b4(
    reworks: list[dict[str, Any]],
    *,
    unique_contribution_ids: set[str],
    reviews_completed: int,
    requests: list[dict[str, Any]],
) -> KpiScore:
    if not reworks:
        if reviews_completed == 0 and not requests:
            return KpiScore(
                kpi_code="B4",
                label="Contribution stability becomes available after review or rework telemetry is tracked.",
                provenance="unknown",
                health="unknown",
                confidence=0.0,
                evidence=["No `rework_requested` events were observed yet."],
            )
        return KpiScore(
            kpi_code="B4",
            value=100.0,
            label="Contribution stability is strong because no blocking rework was observed.",
            provenance="measured",
            health="green",
            confidence=0.82,
            evidence=[
                f"Observed completed reviews: {reviews_completed}.",
                "No tracked rework loop is currently open.",
            ],
        )

    open_blocking = 0
    resolved_blocking = 0
    open_non_blocking = 0
    resolved_non_blocking = 0
    rework_counts_by_contribution: dict[str, int] = {}
    for rework in reworks:
        contribution_id = str(rework.get("contribution_id") or "unknown")
        rework_counts_by_contribution[contribution_id] = rework_counts_by_contribution.get(contribution_id, 0) + 1
        is_blocking = bool(rework.get("is_blocking"))
        resolved = rework.get("resolved_at") is not None
        if is_blocking and not resolved:
            open_blocking += 1
        elif is_blocking and resolved:
            resolved_blocking += 1
        elif not is_blocking and not resolved:
            open_non_blocking += 1
        else:
            resolved_non_blocking += 1

    contribution_base = max(1, len(unique_contribution_ids) or len(rework_counts_by_contribution))
    repeat_penalty = 6 * sum(1 for count in rework_counts_by_contribution.values() if count > 1)
    penalty = (
        (open_blocking * 32)
        + (resolved_blocking * 18)
        + (open_non_blocking * 14)
        + (resolved_non_blocking * 8)
        + repeat_penalty
    ) / contribution_base
    value = round(max(0.0, 100.0 - penalty), 1)
    return KpiScore(
        kpi_code="B4",
        value=value,
        label="Contribution stability derived from blocking and recurring rework loops.",
        provenance="measured",
        health=_health_from_score(value, green=80.0, amber=55.0),
        confidence=0.85,
        evidence=[
            f"Blocking rework open/resolved: {open_blocking}/{resolved_blocking}.",
            f"Non-blocking rework open/resolved: {open_non_blocking}/{resolved_non_blocking}.",
        ],
    )


def _score_e(scores: list[KpiScore]) -> KpiScore:
    weighted_total = 0.0
    total_weight = 0.0
    provenances: set[str] = set()
    evidence: list[str] = []
    measured_scores = [score for score in scores if score.value is not None and score.kpi_code in _OPERATIONAL_WEIGHTS]
    for score in measured_scores:
        weight = _OPERATIONAL_WEIGHTS[score.kpi_code]
        weighted_total += score.value * weight
        total_weight += weight
        provenances.add(score.provenance)
        evidence.append(f"{score.kpi_code}: {score.value}.")

    if total_weight == 0:
        return KpiScore(
            kpi_code="E",
            label="Operational efficiency index becomes available when at least one B KPI is observed.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No operational KPI is currently scoreable."],
        )

    value = round(weighted_total / total_weight, 1)
    provenance = "measured" if provenances == {"measured"} else "inferred"
    confidence = round(sum(score.confidence or 0.0 for score in measured_scores) / max(1, len(measured_scores)), 2)
    return KpiScore(
        kpi_code="E",
        value=value,
        label="Operational efficiency index derived from B1..B4.",
        provenance=provenance,
        health=_health_from_score(value, green=80.0, amber=55.0),
        confidence=confidence,
        evidence=evidence,
    )


def _compute_operational_snapshot(events: list[dict[str, Any]], now: datetime) -> OperationalSnapshot:
    state = _collect_operational_state(events)
    b1 = _score_b1(state.requests, now)
    b2 = _score_b2(state.requests, now)
    b3 = _score_b3(state.calls, now)
    b4 = _score_b4(
        state.reworks,
        unique_contribution_ids=state.unique_contribution_ids,
        reviews_completed=state.reviews_completed,
        requests=state.requests,
    )
    e = _score_e([b1, b2, b3, b4])
    notes = [
        f"Contribution requests tracked: {len(state.requests)}.",
        f"Review cycles started/completed: {state.reviews_started}/{state.reviews_completed}.",
        f"Rework loops tracked: {len(state.reworks)}.",
        f"Call sessions tracked: {len(state.calls)}.",
    ]
    if any(score.value is not None for score in [b1, b2, b3, b4]):
        summary = "Operational telemetry is available and B1..B4 are derived from observed workflow events."
    else:
        summary = "Operational telemetry is not available yet, so B1..B4 remain pending."
    return OperationalSnapshot(b1=b1, b2=b2, b3=b3, b4=b4, e=e, notes=notes, summary=summary)

def _derive_health(scores: list[KpiScore]) -> HealthClass:
    concrete = [score.health for score in scores if score.health != "unknown"]
    if not concrete:
        return "unknown"
    if "red" in concrete:
        return "red"
    if "amber" in concrete:
        return "amber"
    return "green"


def _derive_phase(
    *,
    current_status: str,
    document_ingested: bool,
    requirements_extracted: bool,
    requirement_count: int,
    active_sections: int,
    proposal_updates: int,
    a1_score: KpiScore,
    outcome: str | None,
    submitted: bool,
    operational_state: OperationalState,
) -> str:
    if outcome in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[outcome]

    if _normalized(current_status) in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[_normalized(current_status)]

    if submitted or _normalized(current_status) == "submitted":
        return "S9"

    open_blocking_reworks = sum(
        1 for rework in operational_state.reworks if rework.get("is_blocking") and rework.get("resolved_at") is None
    )
    open_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "open")
    failed_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "failed")
    open_reviews = max(0, operational_state.reviews_started - operational_state.reviews_completed)

    if open_blocking_reworks > 0:
        return "S6"

    if open_gates > 0 or failed_gates > 0:
        return "S8"

    if open_reviews > 0:
        return "S5"

    if not document_ingested:
        return "S0"

    if not requirements_extracted and requirement_count == 0:
        return "S2"

    if requirements_extracted and proposal_updates == 0 and active_sections == 0:
        return "S3"

    if active_sections > 0 and (a1_score.value or 0.0) < 70.0:
        return "S4"

    if active_sections > 0:
        return "S7"

    return "S2"


def compute_analysis_snapshot(
    tender: dict[str, Any] | None,
    events: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> AnalysisSnapshot:
    if tender is None:
        return AnalysisSnapshot(
            analytical_phase=None,
            health="unknown",
            kpis=[],
            notes=["Tender not synchronized yet."],
            summary="Tender not synchronized yet.",
        )

    now = now or datetime.now(timezone.utc)
    requirements = list(tender.get("requirement_contexts") or [])
    sections = list(tender.get("section_contexts") or [])
    current_status = _normalized(tender.get("current_status"))

    document_ingested = _count_events(events, "tender_document_ingested") > 0
    requirements_extracted = _count_events(events, "requirements_extracted") > 0
    proposal_updates = _count_events(events, "proposal_section_updated")
    submitted = _count_events(events, "tender_submitted") > 0 or current_status == "submitted"
    outcome = _latest_outcome(events)

    requirement_count = len(requirements)
    addressed_requirements = sum(
        1
        for requirement in requirements
        if _normalized(requirement.get("compliance_status")) in _ADDRESSED_REQUIREMENT_STATUSES
        or bool(requirement.get("mapped_section_id"))
    )
    high_priority_requirements = sum(
        1 for requirement in requirements if _normalized(requirement.get("priority")) == "high"
    )
    active_sections = sum(
        1 for section in sections if _normalized(section.get("status")) in _ACTIVE_SECTION_STATUSES
    )
    completed_sections = sum(
        1 for section in sections if _normalized(section.get("status")) in _COMPLETED_SECTION_STATUSES
    )

    due_at = _parse_datetime(tender.get("due_at"))
    if document_ingested:
        a1 = _score_a1(
            requirement_count=requirement_count,
            addressed_requirements=addressed_requirements,
            section_count=len(sections),
            active_sections=active_sections,
            proposal_updates=proposal_updates,
            requirements_extracted=requirements_extracted,
        )
        a4 = _score_a4(
            document_ingested=document_ingested,
            requirement_count=requirement_count,
            addressed_requirements=addressed_requirements,
            high_priority_requirements=high_priority_requirements,
            section_count=len(sections),
            active_sections=active_sections,
            due_at=due_at,
            submitted=submitted,
            now=now,
        )
    else:
        a1 = KpiScore(
            kpi_code="A1",
            label="Requirement coverage becomes available after tender document ingestion.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No `tender_document_ingested` event was observed yet."],
        )
        a4 = KpiScore(
            kpi_code="A4",
            label="Compliance readiness becomes available after tender document ingestion.",
            provenance="unknown",
            health="unknown",
            confidence=0.0,
            evidence=["No `tender_document_ingested` event was observed yet."],
        )

    operational = _compute_operational_snapshot(events, now)
    operational_state = _collect_operational_state(events)
    health = _derive_health([a1, a4, operational.b1, operational.b2, operational.b3, operational.b4, operational.e])
    analytical_phase = _derive_phase(
        current_status=current_status,
        document_ingested=document_ingested,
        requirements_extracted=requirements_extracted,
        requirement_count=requirement_count,
        active_sections=active_sections,
        proposal_updates=proposal_updates,
        a1_score=a1,
        outcome=outcome,
        submitted=submitted,
        operational_state=operational_state,
    )

    notes = [
        f"Requirements tracked in mirror: {requirement_count}.",
        f"Proposal sections tracked in mirror: {len(sections)} ({completed_sections} completed).",
        f"Observed `proposal_section_updated` events: {proposal_updates}.",
        *operational.notes,
    ]

    if not document_ingested:
        summary = "Tender mirror is available, but the tender document has not been ingested yet."
    elif requirement_count == 0:
        summary = "Tender document ingestion exists, but extracted requirements are still missing or empty."
    elif any(score.value is not None for score in [operational.b1, operational.b2, operational.b3, operational.b4]):
        summary = (
            "Partial analytical snapshot is available for A1, A4 and B1..B4 using persisted requirements, "
            "proposal progress and observed workflow telemetry."
        )
    else:
        summary = (
            "Partial analytical snapshot is available for A1 and A4 using persisted requirements, "
            "proposal progress and base tender telemetry."
        )

    return AnalysisSnapshot(
        analytical_phase=analytical_phase,
        health=health,
        kpis=[a1, a4, operational.b1, operational.b2, operational.b3, operational.b4, operational.e],
        notes=notes,
        summary=summary,
    )


