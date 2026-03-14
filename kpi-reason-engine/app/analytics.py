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


@dataclass(slots=True)
class AnalysisSnapshot:
    analytical_phase: str | None
    health: HealthClass
    kpis: list[KpiScore]
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
        payload = event.get("payload") or {}
        outcome = _normalized(payload.get("outcome"))
        if outcome:
            return outcome
    return None


def _days_until(due_at: datetime | None, now: datetime) -> float | None:
    if due_at is None:
        return None
    return (due_at - now).total_seconds() / 86400


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
) -> str:
    if outcome in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[outcome]

    if _normalized(current_status) in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[_normalized(current_status)]

    if submitted or _normalized(current_status) == "submitted":
        return "S9"

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
    health = _derive_health([a1, a4])
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
    )

    notes = [
        f"Requirements tracked in mirror: {requirement_count}.",
        f"Proposal sections tracked in mirror: {len(sections)} ({completed_sections} completed).",
        f"Observed `proposal_section_updated` events: {proposal_updates}.",
    ]

    if not document_ingested:
        summary = "Tender mirror is available, but the tender document has not been ingested yet."
    elif requirement_count == 0:
        summary = "Tender document ingestion exists, but extracted requirements are still missing or empty."
    else:
        summary = (
            "Partial analytical snapshot is available for A1 and A4 using persisted requirements, "
            "proposal progress and base tender telemetry."
        )

    return AnalysisSnapshot(
        analytical_phase=analytical_phase,
        health=health,
        kpis=[a1, a4],
        notes=notes,
        summary=summary,
    )

