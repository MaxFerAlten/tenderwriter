"""Deterministic analytical scoring helpers for the KPI reason engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.contract import (
    AMBER_E_THRESHOLD,
    AMBER_Q_THRESHOLD,
    FORMULA_BUNDLE_VERSION,
    GREEN_A4_THRESHOLD,
    GREEN_E_THRESHOLD,
    GREEN_Q_THRESHOLD,
    HEALTH_RULE_VERSION,
    KPI_CONTRACT_VERSION,
    MARKOV_PHASE_SCOPE,
    MARKOV_RELIABLE_PHASE_SCOPE,
    MODEL_BUNDLE_VERSION,
    OPERATIONAL_WEIGHTS,
    PROMPT_BUNDLE_VERSION,
    QUALITY_WEIGHTS,
    QUALITATIVE_ENGINE_PROXY,
    QUALITATIVE_ENGINE_SEMANTIC,
    QUALITATIVE_ENGINE_SHADOW,
    SCORE_SCALE_EXTERNAL,
    SNAPSHOT_OUTPUT_SCHEMA_VERSION,
    SCORE_SCALE_INTERNAL,
    SEMANTIC_BUNDLE_VERSION,
    SEMANTIC_ENGINE_KIND,
    SEMANTIC_EXECUTION_MODE,
    SEMANTIC_FALLBACK_POLICY_VERSION,
    SEMANTIC_FORMULA_VERSIONS,
    SEMANTIC_MODEL_VERSION,
    SEMANTIC_PRIORITY,
    SEMANTIC_PROMPT_VERSION,
    SEMANTIC_SUPPORTED_KPIS,
    SHADOW_BUNDLE_VERSION,
    SHADOW_ENGINE_KIND,
    SHADOW_EXECUTION_MODE,
    SHADOW_SUPPORTED_KPIS,
    normalize_source_type,
)
from app.schemas import HealthClass, KpiScore, SemanticEvaluation, SemanticShadowEvaluation
from app.semantic_engine import build_a1_semantic, build_a2_semantic, build_a3_semantic, build_a4_semantic
from app.semantic_shadow import build_a1_shadow, build_a4_shadow

_ACTIVE_SECTION_STATUSES = {"in_progress", "in_review", "approved", "submitted"}
_COMPLETED_SECTION_STATUSES = {"approved", "submitted"}
_ADDRESSED_REQUIREMENT_STATUSES = {"partially_addressed", "fully_addressed"}
_TERMINAL_PHASES = {
    "won": "S11",
    "win": "S11",
    "lost": "S12",
    "loss": "S12",
    "stopped": "S13",
    "cancelled": "S13",
    "canceled": "S13",
    "excluded": "S13",
    "withdrawn": "S13",
    "no-bid": "S13",
    "no_bid": "S13",
}
_FORMULA_BUNDLE_VERSION = FORMULA_BUNDLE_VERSION
_MODEL_BUNDLE_VERSION = MODEL_BUNDLE_VERSION
_PROMPT_BUNDLE_VERSION = PROMPT_BUNDLE_VERSION
_OPERATIONAL_WEIGHTS = OPERATIONAL_WEIGHTS
_QUALITY_WEIGHTS = QUALITY_WEIGHTS
_KPI_VERSION_MAP = {
    "A1": {"formula_version": "requirement-coverage-v2", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "A2": {"formula_version": "editorial-quality-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "A3": {"formula_version": "competitiveness-value-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "A4": {"formula_version": "compliance-readiness-v2", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "Q": {"formula_version": "qualitative-index-v2", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "B1": {"formula_version": "deadline-adherence-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "B2": {"formula_version": "sla-responsiveness-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "B3": {"formula_version": "call-participation-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "B4": {"formula_version": "rework-stability-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
    "E": {"formula_version": "operational-efficiency-v1", "model_version": _MODEL_BUNDLE_VERSION, "prompt_version": _PROMPT_BUNDLE_VERSION},
}


@dataclass(slots=True)
class AnalysisSnapshot:
    analytical_phase: str | None
    health: HealthClass
    kpis: list[KpiScore]
    notes: list[str]
    summary: str
    analysis_metadata: dict[str, Any]


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


def _severity_from_score(value: float | None, health: HealthClass) -> str:
    if health == "unknown":
        return "unknown"
    if health == "green":
        return "none" if value is not None and value >= 95.0 else "low"
    if health == "amber":
        return "medium"
    if value is not None and value < 25.0:
        return "critical"
    return "high"


def _combine_provenance(scores: list[KpiScore]) -> str:
    provenances = {
        normalize_source_type(score.source_type or score.provenance)
        for score in scores
        if normalize_source_type(score.source_type or score.provenance) != "unknown"
    }
    if not provenances:
        return "unknown"
    if "reconstructed" in provenances:
        return "reconstructed"
    if "inferred" in provenances:
        return "inferred"
    if provenances == {"observed"}:
        return "observed"
    return "unknown"


def _weighted_confidence(scores: list[KpiScore], weights: dict[str, float] | None = None) -> float:
    weighted_total = 0.0
    total_weight = 0.0
    for score in scores:
        if score.confidence is None:
            continue
        weight = 1.0 if weights is None else weights.get(score.kpi_code, 0.0)
        if weight <= 0:
            continue
        weighted_total += score.confidence * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return round(weighted_total / total_weight, 2)


def _count_events(events: list[dict[str, Any]], event_type: str) -> int:
    target = _normalized(event_type)
    return sum(1 for event in events if _normalized(event.get("event_type")) == target)


def _latest_outcome(events: list[dict[str, Any]]) -> str | None:
    direct_event_map = {
        "award_confirmed": "won",
        "loss_reason_recorded": "lost",
        "tender_excluded": "excluded",
        "tender_withdrawn": "withdrawn",
        "tender_stopped": "stopped",
        "tender_stopped_at_gate": "stopped",
        "no_bid_decision_recorded": "no_bid",
    }
    for event in reversed(events):
        event_type = _normalized(event.get("event_type"))
        if event_type == "tender_outcome_recorded":
            payload = _event_payload(event)
            outcome = _normalized(payload.get("outcome"))
            if outcome:
                return outcome
        mapped = direct_event_map.get(event_type)
        if mapped:
            return mapped
    return None


def _latest_decision(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        event_type = _normalized(event.get("event_type"))
        if event_type == "go_decision_recorded":
            return "go"
        if event_type == "no_bid_decision_recorded":
            return "no_bid"
    return None


def _latest_submission_state(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        event_type = _normalized(event.get("event_type"))
        if event_type == "submission_failed":
            return "failed"
        if event_type == "submission_acknowledged":
            return "acknowledged"
        if event_type == "tender_submitted":
            return "submitted"
    return None


def _clarification_active(events: list[dict[str, Any]]) -> bool:
    named_clarifications: dict[str, bool] = {}
    unnamed_open_count = 0

    for event in events:
        event_type = _normalized(event.get("event_type"))
        if event_type not in {
            "clarification_requested",
            "clarification_response_drafted",
            "clarification_submitted",
            "clarification_closed",
        }:
            continue

        payload = _event_payload(event)
        request_id = payload.get("request_id")
        normalized_request_id = str(request_id).strip() if request_id is not None else ""
        is_open_event = event_type != "clarification_closed"

        if normalized_request_id:
            named_clarifications[normalized_request_id] = is_open_event
            continue

        if is_open_event:
            unnamed_open_count += 1
        else:
            unnamed_open_count = max(0, unnamed_open_count - 1)

    return unnamed_open_count > 0 or any(named_clarifications.values())

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


def _version_fields(kpi_code: str) -> dict[str, Any]:
    return dict(_KPI_VERSION_MAP.get(kpi_code, {}))


def _build_score(
    *,
    kpi_code: str,
    value: float | None = None,
    label: str | None = None,
    provenance: str = "unknown",
    health: HealthClass = "unknown",
    confidence: float | None = None,
    evidence: list[str] | None = None,
    recommendation: str | None = None,
    criticalities: list[str] | None = None,
    severity: str | None = None,
) -> KpiScore:
    canonical_source_type = normalize_source_type(provenance)
    evidence_items = list(evidence or [])
    recommendation_items = [recommendation] if recommendation else []
    return KpiScore(
        kpi_code=kpi_code,
        score=value,
        value=value,
        label=label,
        source_type=canonical_source_type,
        provenance=canonical_source_type,
        health=health,
        confidence=confidence,
        evidences=evidence_items,
        evidence=evidence_items,
        criticalities=list(criticalities or []),
        recommendations=recommendation_items,
        recommendation=recommendation,
        severity=severity or _severity_from_score(value, health),
        **_version_fields(kpi_code),
    )


def _unknown_score(*, kpi_code: str, label: str, evidence: list[str], recommendation: str) -> KpiScore:
    return _build_score(
        kpi_code=kpi_code,
        label=label,
        provenance="unknown",
        health="unknown",
        confidence=0.0,
        evidence=evidence,
        recommendation=recommendation,
        severity="unknown",
    )


def _with_shadow(score: KpiScore, shadow: SemanticShadowEvaluation | None) -> KpiScore:
    if shadow is None:
        return score
    payload = score.model_dump(mode="python")
    payload["shadow"] = shadow.model_dump(mode="python")
    return KpiScore(**payload)



def _override_score_contract(
    score: KpiScore,
    *,
    formula_version: str | None = None,
    model_version: str | None = None,
    prompt_version: str | None = None,
    label: str | None = None,
) -> KpiScore:
    payload = score.model_dump(mode="python")
    if formula_version is not None:
        payload["formula_version"] = formula_version
    if model_version is not None:
        payload["model_version"] = model_version
    if prompt_version is not None:
        payload["prompt_version"] = prompt_version
    if label is not None:
        payload["label"] = label
    return KpiScore(**payload)



def _with_semantic(score: KpiScore, semantic: SemanticEvaluation | None) -> KpiScore:
    if semantic is None:
        return score

    payload = score.model_dump(mode="python")
    semantic_payload = semantic.model_dump(mode="python")

    if semantic.semantic_score is None:
        if score.value is not None:
            semantic_payload["status"] = "fallback"
            semantic_payload["fallback_reason"] = semantic_payload.get("fallback_reason") or "semantic_score_not_available"
        payload["semantic"] = semantic_payload
        return KpiScore(**payload)

    recommendations = list(semantic.recommendations or [])
    payload["semantic"] = semantic_payload
    payload["score"] = semantic.semantic_score
    payload["value"] = semantic.semantic_score
    payload["health"] = semantic.health
    payload["source_type"] = semantic.source_type
    payload["provenance"] = semantic.source_type
    payload["confidence"] = semantic.confidence
    payload["evidences"] = list(semantic.evidences or [])
    payload["evidence"] = list(semantic.evidences or [])
    payload["criticalities"] = list(semantic.criticalities or [])
    payload["recommendations"] = recommendations
    payload["recommendation"] = recommendations[0] if recommendations else None
    payload["formula_version"] = semantic.formula_version
    payload["model_version"] = semantic.model_version
    payload["prompt_version"] = semantic.prompt_version
    return KpiScore(**payload)



def _with_qualitative_summary_contract(score: KpiScore) -> KpiScore:
    return _override_score_contract(
        score,
        formula_version=SEMANTIC_FORMULA_VERSIONS["Q"],
        model_version=SEMANTIC_MODEL_VERSION,
        prompt_version=SEMANTIC_PROMPT_VERSION,
        label="Qualitative quality index derived from official semantic A1..A4.",
    )

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
            return _unknown_score(
                kpi_code="A1",
                label="Requirement coverage is waiting for extracted requirements.",
                evidence=["No `requirements_extracted` event was observed yet."],
                recommendation="Complete tender ingestion and requirement extraction before evaluating requirement coverage.",
            )

        return _build_score(
            kpi_code="A1",
            value=0.0,
            label="No tender requirements were extracted from the uploaded document.",
            provenance="inferred",
            health="red",
            confidence=0.55,
            evidence=["The tender document was processed but yielded zero persisted requirements."],
            recommendation="Review requirement extraction and create the missing requirement baseline before progressing the proposal.",
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
    health = _health_from_score(value, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)
    if health == "green":
        recommendation = "Keep the requirement-to-section mapping current and preserve traceability for final compliance review."
    elif health == "amber":
        recommendation = "Map the remaining requirements to concrete sections and close partially addressed items before the next gate."
    else:
        recommendation = "Stop adding new narrative until the missing requirements are mapped, assigned and addressed in the proposal structure."
    return _build_score(
        kpi_code="A1",
        value=value,
        label="Requirement coverage proxy built from persisted requirements and proposal progress.",
        provenance=provenance,
        health=health,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
    )


def _score_a2(
    *,
    document_ingested: bool,
    sections: list[dict[str, Any]],
    requirement_count: int,
    addressed_requirements: int,
    completed_sections: int,
    proposal_updates: int,
    operational_state: OperationalState,
) -> KpiScore:
    if not document_ingested:
        return _unknown_score(
            kpi_code="A2",
            label="Editorial quality becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document and sync proposal sections before evaluating editorial quality.",
        )

    section_count = len(sections)
    if section_count == 0:
        return _build_score(
            kpi_code="A2",
            value=0.0,
            label="Editorial quality is blocked because no proposal sections are tracked yet.",
            provenance="inferred",
            health="red",
            confidence=0.54,
            evidence=["The tender has no mirrored proposal sections to evaluate narrative maturity."],
            recommendation="Create and structure the proposal sections before evaluating narrative quality or readability.",
        )

    meaningful_titles = sum(1 for section in sections if len(str(section.get("title") or "").strip()) >= 8)
    title_quality_ratio = meaningful_titles / section_count
    progress_ratio = completed_sections / section_count if section_count else 0.0
    review_closure_ratio = (
        operational_state.reviews_completed / operational_state.reviews_started
        if operational_state.reviews_started
        else (0.65 if completed_sections > 0 else 0.25)
    )
    open_reworks = sum(1 for rework in operational_state.reworks if rework.get("resolved_at") is None)
    rework_penalty = min((open_reworks + (len(operational_state.reworks) * 0.35)) / max(1, section_count), 1.0)
    alignment_ratio = addressed_requirements / requirement_count if requirement_count else min(section_count / 3.0, 1.0)
    update_ratio = min(proposal_updates / max(1, section_count), 1.0)

    value = round(
        (
            (title_quality_ratio * 0.10)
            + (progress_ratio * 0.25)
            + (review_closure_ratio * 0.25)
            + ((1.0 - rework_penalty) * 0.20)
            + (alignment_ratio * 0.10)
            + (update_ratio * 0.10)
        )
        * 100,
        1,
    )

    provenance = "measured" if operational_state.reviews_started or operational_state.reworks else "inferred"
    confidence = 0.86 if provenance == "measured" else round(min(0.79, 0.58 + (section_count * 0.05)), 2)
    health = _health_from_score(value, green=GREEN_Q_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    if open_reworks > 0:
        recommendation = "Resolve open rework loops and stabilize the latest section revisions before claiming editorial readiness."
    elif health == "green":
        recommendation = "Maintain the current editorial cadence and keep section reviews flowing to preserve narrative consistency."
    elif health == "amber":
        recommendation = "Tighten section wording, complete the pending reviews and push more sections into approved state."
    else:
        recommendation = "Formalize the proposal structure, complete section drafting and start review cycles before evaluating redaction quality."

    return _build_score(
        kpi_code="A2",
        value=value,
        label="Editorial quality proxy built from section maturity, review closure and rework pressure.",
        provenance=provenance,
        health=health,
        confidence=confidence,
        evidence=[
            f"Proposal sections tracked: {section_count}, with {completed_sections} completed.",
            f"Sections with meaningful titles: {meaningful_titles}/{section_count}.",
            f"Review cycles started/completed: {operational_state.reviews_started}/{operational_state.reviews_completed}.",
            f"Open rework loops: {open_reworks}; proposal section updates observed: {proposal_updates}.",
        ],
        recommendation=recommendation,
    )


def _score_a3(
    *,
    document_ingested: bool,
    requirement_count: int,
    addressed_requirements: int,
    high_priority_requirements: int,
    addressed_high_priority_requirements: int,
    section_count: int,
    completed_sections: int,
    proposal_updates: int,
    operational_state: OperationalState,
) -> KpiScore:
    if not document_ingested:
        return _unknown_score(
            kpi_code="A3",
            label="Competitive and technical value becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document and establish requirement coverage before evaluating competitiveness.",
        )

    if requirement_count == 0:
        return _build_score(
            kpi_code="A3",
            value=0.0,
            label="Competitive and technical value is blocked because no requirements are available.",
            provenance="inferred",
            health="red",
            confidence=0.56,
            evidence=["The tender has no persisted requirement baseline to assess competitive fit."],
            recommendation="Recover the requirement baseline first, then align the proposal with the highest-priority asks.",
        )

    high_priority_focus = (
        addressed_high_priority_requirements / high_priority_requirements
        if high_priority_requirements
        else addressed_requirements / requirement_count
    )
    delivery_depth = completed_sections / section_count if section_count else 0.0
    open_blocking_reworks = sum(
        1 for rework in operational_state.reworks if rework.get("is_blocking") and rework.get("resolved_at") is None
    )
    failed_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "failed")
    open_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "open")
    blocker_ratio = min(
        ((open_blocking_reworks * 1.0) + (failed_gates * 1.0) + (open_gates * 0.6))
        / max(1, high_priority_requirements or requirement_count),
        1.0,
    )
    review_depth = min((operational_state.reviews_completed + proposal_updates) / max(1, requirement_count), 1.0)
    request_coverage = min(len(operational_state.requests) / max(1, section_count or requirement_count), 1.0)

    value = round(
        (
            (high_priority_focus * 0.45)
            + (delivery_depth * 0.20)
            + ((1.0 - blocker_ratio) * 0.25)
            + (review_depth * 0.05)
            + (request_coverage * 0.05)
        )
        * 100,
        1,
    )

    provenance = "measured" if (operational_state.gates or operational_state.reviews_started or operational_state.reworks) else "inferred"
    confidence = 0.84 if provenance == "measured" else 0.72
    health = _health_from_score(value, green=GREEN_Q_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    if open_blocking_reworks > 0 or failed_gates > 0:
        recommendation = "Close blocking rework and failed gates on high-priority requirements before presenting the offer as competitive."
    elif health == "green":
        recommendation = "Protect the current technical positioning by keeping high-priority requirements fully covered through final submission."
    elif health == "amber":
        recommendation = "Increase coverage on the highest-priority requirements and complete more sections to strengthen the offer value."
    else:
        recommendation = "Refocus the proposal on the highest-priority requirements and remove unresolved blockers that weaken technical credibility."

    return _build_score(
        kpi_code="A3",
        value=value,
        label="Competitive and technical value proxy derived from high-priority coverage, delivery depth and blocker pressure.",
        provenance=provenance,
        health=health,
        confidence=confidence,
        evidence=[
            f"High-priority requirements addressed: {addressed_high_priority_requirements}/{high_priority_requirements or requirement_count}.",
            f"Completed proposal sections: {completed_sections}/{section_count or 0}.",
            f"Blocking rework open: {open_blocking_reworks}; open/failed gates: {open_gates}/{failed_gates}.",
            f"Review completions plus section updates observed: {operational_state.reviews_completed + proposal_updates}.",
        ],
        recommendation=recommendation,
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
        return _unknown_score(
            kpi_code="A4",
            label="Compliance readiness becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document and extract requirements before evaluating compliance readiness.",
        )

    if requirement_count == 0:
        return _build_score(
            kpi_code="A4",
            value=0.0,
            label="Compliance readiness is blocked because no requirements are available.",
            provenance="inferred",
            health="red",
            confidence=0.58,
            evidence=["The tender cannot establish compliance readiness without extracted requirements."],
            recommendation="Restore the requirement baseline and map each item to a section before opening compliance gates.",
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
    health = _health_from_score(value, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)
    if health == "green":
        recommendation = "Keep the compliance map synchronized and preserve enough time buffer before submission."
    elif health == "amber":
        recommendation = "Close unresolved requirements and reduce deadline pressure before the next compliance gate."
    else:
        recommendation = "Escalate missing requirements and deadline risk immediately; the tender is not yet ready for a compliance decision."
    return _build_score(
        kpi_code="A4",
        value=value,
        label="Compliance readiness proxy combining requirement backlog, proposal progress and deadline pressure.",
        provenance="inferred",
        health=health,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
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

        if event_type in {"review_cycle_started", "contribution_review_started"}:
            reviews_started += 1
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            continue

        if event_type in {"contribution_review_completed", "review_approved", "review_changes_requested"}:
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
        if event_type in {"coordination_risk_raised", "compliance_gate_rework_requested"}:
            default_rework_id = (
                f"gate-rework-{payload.get('external_gate_id') or index}"
                if event_type == "compliance_gate_rework_requested"
                else f"coordination-risk-{index}"
            )
            rework_id = str(payload.get("external_rework_id") or default_rework_id)
            contribution_id = str(payload.get("external_contribution_id") or "")
            if contribution_id:
                unique_contribution_ids.add(contribution_id)
            reworks[rework_id] = {
                "rework_id": rework_id,
                "contribution_id": contribution_id,
                "requested_at": _parse_datetime(payload.get("requested_at")) or occurred_at,
                "resolved_at": None,
                "is_blocking": bool(payload.get("is_blocking", True)),
                "severity": _normalized(payload.get("severity")) or "high",
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
        if event_type == "rework_reescalated_to_coordination":
            rework_id = str(payload.get("external_rework_id") or f"coordination-recovery-{index}")
            current = reworks.setdefault(
                rework_id,
                {
                    "rework_id": rework_id,
                    "contribution_id": str(payload.get("external_contribution_id") or ""),
                    "requested_at": _parse_datetime(payload.get("requested_at")),
                    "is_blocking": bool(payload.get("is_blocking", True)),
                    "severity": _normalized(payload.get("severity")) or "high",
                },
            )
            current["resolved_at"] = _parse_datetime(payload.get("resolved_at")) or occurred_at
            continue

        if event_type == "compliance_gate_opened":
            gate_id = str(payload.get("external_gate_id") or f"gate-{index}")
            gates[gate_id] = {"gate_id": gate_id, "status": "open", "gate_name": payload.get("gate_name")}
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
        return _unknown_score(
            kpi_code="B1",
            label="Deadline adherence becomes available after at least one tracked contribution request.",
            evidence=["No `contribution_request_created` events were observed yet."],
            recommendation="Track contribution requests and due dates before evaluating delivery adherence.",
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
    health = _health_from_score(value, green=80.0, amber=55.0)
    if health == "green":
        recommendation = "Keep the current request management cadence and protect due dates on new contribution asks."
    elif health == "amber":
        recommendation = "Shorten the response queue and push overdue requests back on track before the next milestone."
    else:
        recommendation = "Escalate overdue contribution requests immediately and rebalance due dates before delivery adherence degrades further."
    return _build_score(
        kpi_code="B1",
        value=value,
        label="Deadline adherence across tracked contribution requests.",
        provenance="measured",
        health=health,
        confidence=0.88,
        evidence=[
            f"Tracked contribution requests: {len(requests)}.",
            f"On-time deliveries: {on_time}, late deliveries: {late}, overdue open requests: {overdue_open}.",
        ],
        recommendation=recommendation,
    )


def _score_b2(requests: list[dict[str, Any]], now: datetime) -> KpiScore:
    eligible = [request for request in requests if request.get("requested_at") is not None]
    if not eligible:
        return _unknown_score(
            kpi_code="B2",
            label="Operational responsiveness becomes available after requests are tracked with timestamps.",
            evidence=["No request/response cycle with timestamps was observed yet."],
            recommendation="Track request timestamps and SLA thresholds before evaluating responsiveness.",
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
        return _unknown_score(
            kpi_code="B2",
            label="Operational responsiveness has no scoreable request cycle yet.",
            evidence=["Tracked requests were missing sufficient timing data."],
            recommendation="Improve request telemetry completeness before evaluating SLA responsiveness.",
        )

    value = round(sum(scores) / len(scores), 1)
    health = _health_from_score(value, green=80.0, amber=55.0)
    if health == "green":
        recommendation = "Maintain the current SLA response discipline and preserve fast turnaround on clarifications."
    elif health == "amber":
        recommendation = "Reduce SLA drift on slower requests before it starts affecting downstream reviews and gates."
    else:
        recommendation = "Escalate the breached request cycles and reallocate ownership until the response path returns inside SLA."
    return _build_score(
        kpi_code="B2",
        value=value,
        label="Operational responsiveness against SLA target and maximum thresholds.",
        provenance="measured",
        health=health,
        confidence=0.86,
        evidence=[
            f"Requests scored for responsiveness: {len(scores)}.",
            f"Within SLA target: {within_target}, within SLA max: {within_max}, breached: {breached}.",
        ],
        recommendation=recommendation,
    )


def _score_b3(calls: list[dict[str, Any]], now: datetime) -> KpiScore:
    attendance_calls = [call for call in calls if call.get("attendance")]
    if not attendance_calls:
        return _unknown_score(
            kpi_code="B3",
            label="Call participation becomes available after attendance is recorded.",
            evidence=["No `call_attendance_recorded` events were observed yet."],
            recommendation="Track call attendance before using participation as an operational health signal.",
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
    health = _health_from_score(value, green=80.0, amber=55.0)
    if health == "green":
        recommendation = "Keep the current coordination cadence and continue recording attendance consistently."
    elif health == "amber":
        recommendation = "Tighten call participation on key contributors before coordination gaps create rework."
    else:
        recommendation = "Escalate low participation and re-establish a reliable coordination forum for the tender workstream."
    return _build_score(
        kpi_code="B3",
        value=value,
        label="Participation rate across scheduled tender calls with recorded attendance.",
        provenance="measured",
        health=health,
        confidence=0.84,
        evidence=[
            f"Calls with attendance records: {len(attendance_calls)}.",
            f"Recorded participants attended: {total_attended}/{total_expected or 0}.",
        ],
        recommendation=recommendation,
    )


def _score_b4(reworks: list[dict[str, Any]], *, unique_contribution_ids: set[str], reviews_completed: int, requests: list[dict[str, Any]]) -> KpiScore:
    if not reworks:
        if reviews_completed == 0 and not requests:
            return _unknown_score(
                kpi_code="B4",
                label="Contribution stability becomes available after review or rework telemetry is tracked.",
                evidence=["No `rework_requested` events were observed yet."],
                recommendation="Track review and rework loops before using contribution stability as an operational KPI.",
            )
        return _build_score(
            kpi_code="B4",
            value=100.0,
            label="Contribution stability is strong because no blocking rework was observed.",
            provenance="measured",
            health="green",
            confidence=0.82,
            evidence=[f"Observed completed reviews: {reviews_completed}.", "No tracked rework loop is currently open."],
            recommendation="Keep the current review discipline and preserve fast closure on new findings to maintain stability.",
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
    penalty = ((open_blocking * 32) + (resolved_blocking * 18) + (open_non_blocking * 14) + (resolved_non_blocking * 8) + repeat_penalty) / contribution_base
    value = round(max(0.0, 100.0 - penalty), 1)
    health = _health_from_score(value, green=80.0, amber=55.0)
    if open_blocking > 0:
        recommendation = "Close the blocking rework loops before new draft iterations amplify instability across contributions."
    elif health == "green":
        recommendation = "Keep rework closure tight and avoid repeated loops on the same contribution areas."
    elif health == "amber":
        recommendation = "Reduce recurring rework and push pending fixes to closure before the next review cycle."
    else:
        recommendation = "Stabilize the contribution flow immediately; recurring and unresolved rework is eroding delivery reliability."
    return _build_score(
        kpi_code="B4",
        value=value,
        label="Contribution stability derived from blocking and recurring rework loops.",
        provenance="measured",
        health=health,
        confidence=0.85,
        evidence=[
            f"Blocking rework open/resolved: {open_blocking}/{resolved_blocking}.",
            f"Non-blocking rework open/resolved: {open_non_blocking}/{resolved_non_blocking}.",
        ],
        recommendation=recommendation,
    )


def _score_q(scores: list[KpiScore]) -> KpiScore:
    measured_scores = [score for score in scores if score.value is not None and score.kpi_code in _QUALITY_WEIGHTS]
    if not measured_scores:
        return _unknown_score(
            kpi_code="Q",
            label="Qualitative index becomes available when A1..A4 are scoreable.",
            evidence=["No qualitative KPI is currently scoreable."],
            recommendation="Score A1..A4 first so the overall qualitative index can be computed.",
        )

    weighted_total = 0.0
    total_weight = 0.0
    evidence: list[str] = []
    for score in measured_scores:
        weight = _QUALITY_WEIGHTS[score.kpi_code]
        weighted_total += (score.value or 0.0) * weight
        total_weight += weight
        evidence.append(f"{score.kpi_code}: {score.value} ({score.health}).")

    value = round(weighted_total / total_weight, 1)
    health = _health_from_score(value, green=GREEN_Q_THRESHOLD, amber=AMBER_Q_THRESHOLD)
    if not measured_scores:
        return _unknown_score(
            kpi_code="Q",
            label="Qualitative index becomes available when A1..A4 are scoreable.",
            evidence=["No qualitative KPI is currently scoreable."],
            recommendation="Score A1..A4 first so the overall qualitative index can be computed.",
        )
    weakest = min(measured_scores, key=lambda score: score.value if score.value is not None else 0.0)
    recommendation = weakest.recommendation or "Improve the weakest qualitative KPI before progressing the tender."
    return _build_score(
        kpi_code="Q",
        value=value,
        label="Qualitative quality index derived from A1..A4.",
        provenance=_combine_provenance(measured_scores),
        health=health,
        confidence=_weighted_confidence(measured_scores, _QUALITY_WEIGHTS),
        evidence=evidence,
        recommendation=f"Priority focus: {weakest.kpi_code}. {recommendation}",
    )


def _score_e(scores: list[KpiScore]) -> KpiScore:
    weighted_total = 0.0
    total_weight = 0.0
    evidence: list[str] = []
    measured_scores = [score for score in scores if score.value is not None and score.kpi_code in _OPERATIONAL_WEIGHTS]
    for score in measured_scores:
        weight = _OPERATIONAL_WEIGHTS[score.kpi_code]
        weighted_total += (score.value or 0.0) * weight
        total_weight += weight
        evidence.append(f"{score.kpi_code}: {score.value} ({score.health}).")

    if total_weight == 0:
        return _unknown_score(
            kpi_code="E",
            label="Operational efficiency index becomes available when at least one B KPI is observed.",
            evidence=["No operational KPI is currently scoreable."],
            recommendation="Track B1..B4 telemetry before using operational efficiency as a summary index.",
        )

    value = round(weighted_total / total_weight, 1)
    if not measured_scores:
        return _unknown_score(
            kpi_code="E",
            label="Operational efficiency index becomes available when at least one B KPI is observed.",
            evidence=["No operational KPI is currently scoreable."],
            recommendation="Track B1..B4 telemetry before using operational efficiency as a summary index.",
        )
    weakest = min(measured_scores, key=lambda score: score.value if score.value is not None else 0.0)
    return _build_score(
        kpi_code="E",
        value=value,
        label="Operational efficiency index derived from B1..B4.",
        provenance=_combine_provenance(measured_scores),
        health=_health_from_score(value, green=GREEN_E_THRESHOLD, amber=AMBER_E_THRESHOLD),
        confidence=_weighted_confidence(measured_scores, _OPERATIONAL_WEIGHTS),
        evidence=evidence,
        recommendation=f"Priority focus: {weakest.kpi_code}. {weakest.recommendation or 'Reduce the weakest operational bottleneck.'}",
    )

def _compute_operational_snapshot(events: list[dict[str, Any]], now: datetime, *, state: OperationalState | None = None) -> OperationalSnapshot:
    state = state or _collect_operational_state(events)
    b1 = _score_b1(state.requests, now)
    b2 = _score_b2(state.requests, now)
    b3 = _score_b3(state.calls, now)
    b4 = _score_b4(state.reworks, unique_contribution_ids=state.unique_contribution_ids, reviews_completed=state.reviews_completed, requests=state.requests)
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


def _derive_health(*, scores: list[KpiScore], q_score: KpiScore, e_score: KpiScore, a4_score: KpiScore, failed_gates: int) -> HealthClass:
    concrete = [score.health for score in scores if score.health != "unknown"]
    q_value = q_score.value
    e_value = e_score.value
    a4_value = a4_score.value
    if not concrete:
        return "unknown"
    if failed_gates > 0:
        return "red"
    if any(score.health == "red" for score in scores if score.kpi_code not in {"Q", "E"}):
        return "red"
    if q_value is not None and e_value is not None and a4_value is not None and q_value >= GREEN_Q_THRESHOLD and e_value >= GREEN_E_THRESHOLD and a4_value >= GREEN_A4_THRESHOLD:
        return "green"
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
    submission_failed: bool,
    clarification_requested: bool,
    decision: str | None,
    bid_plan_started: bool,
    request_wave_opened: bool,
    draft_ready: bool,
    execution_started: bool,
    operational_state: OperationalState,
) -> str:
    normalized_status = _normalized(current_status)
    if outcome in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[outcome]
    if normalized_status in _TERMINAL_PHASES:
        return _TERMINAL_PHASES[normalized_status]
    if decision == "no_bid":
        return "S13"
    if clarification_requested:
        return "S10"
    if submission_failed:
        return "S8"
    if submitted or normalized_status == "submitted":
        return "S9"

    open_blocking_reworks = sum(1 for rework in operational_state.reworks if rework.get("is_blocking") and rework.get("resolved_at") is None)
    open_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "open")
    failed_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "failed")
    open_reviews = max(0, operational_state.reviews_started - operational_state.reviews_completed)

    if open_blocking_reworks > 0:
        return "S6"
    if open_gates > 0 or failed_gates > 0:
        return "S8"
    if open_reviews > 0:
        return "S5"
    if draft_ready:
        return "S7"
    if execution_started:
        return "S4"
    if request_wave_opened:
        return "S3"
    if bid_plan_started or decision == "go":
        return "S2"
    if document_ingested and not decision and not bid_plan_started and not request_wave_opened and proposal_updates == 0 and active_sections == 0:
        return "S1"
    if not document_ingested:
        return "S0"
    if not requirements_extracted and requirement_count == 0:
        return "S1" if document_ingested else "S0"
    if requirements_extracted and proposal_updates == 0 and active_sections == 0:
        return "S3"
    if active_sections > 0 and (a1_score.value or 0.0) < 70.0:
        return "S4"
    return "S2"

def _analysis_metadata(*, events: list[dict[str, Any]], requirement_count: int, section_count: int, scored_kpis: list[KpiScore]) -> dict[str, Any]:
    semantic_official_enabled = settings.semantic_official_rollout_enabled
    shadow_rollout_enabled = settings.semantic_shadow_rollout_enabled
    semantic_kpis = [score.kpi_code for score in scored_kpis if score.semantic is not None]
    semantic_fallback_kpis = [
        score.kpi_code
        for score in scored_kpis
        if score.semantic is not None and score.semantic.status == "fallback"
    ]
    shadow_kpis = [score.kpi_code for score in scored_kpis if score.shadow is not None]

    if semantic_official_enabled:
        qualitative_engine_kind = QUALITATIVE_ENGINE_SEMANTIC
    elif shadow_rollout_enabled:
        qualitative_engine_kind = QUALITATIVE_ENGINE_SHADOW
    else:
        qualitative_engine_kind = QUALITATIVE_ENGINE_PROXY

    return {
        "contract_version": KPI_CONTRACT_VERSION,
        "health_rule_version": HEALTH_RULE_VERSION,
        "score_scale_internal": SCORE_SCALE_INTERNAL,
        "score_scale_external": SCORE_SCALE_EXTERNAL,
        "formula_bundle_version": _FORMULA_BUNDLE_VERSION,
        "model_bundle_version": _MODEL_BUNDLE_VERSION,
        "prompt_bundle_version": _PROMPT_BUNDLE_VERSION,
        "snapshot_output_schema_version": SNAPSHOT_OUTPUT_SCHEMA_VERSION,
        "markov_phase_scope": list(MARKOV_PHASE_SCOPE),
        "markov_reliable_phase_scope": list(MARKOV_RELIABLE_PHASE_SCOPE),
        "semantic_priority": list(SEMANTIC_PRIORITY),
        "canonical_source_types": ["observed", "inferred", "reconstructed", "unknown"],
        "rollout_policy": settings.normalized_rollout_policy,
        "qualitative_engine_kind": qualitative_engine_kind,
        "qualitative_engine_mode": settings.qualitative_engine_mode,
        "semantic_official_enabled": semantic_official_enabled,
        "semantic_engine_kind": SEMANTIC_ENGINE_KIND if semantic_official_enabled else None,
        "semantic_execution_mode": SEMANTIC_EXECUTION_MODE if semantic_official_enabled else None,
        "semantic_bundle_version": SEMANTIC_BUNDLE_VERSION if semantic_official_enabled else None,
        "semantic_kpis": semantic_kpis or (list(SEMANTIC_SUPPORTED_KPIS) if semantic_official_enabled else []),
        "semantic_fallback_kpis": semantic_fallback_kpis,
        "semantic_fallback_policy_version": SEMANTIC_FALLBACK_POLICY_VERSION if semantic_official_enabled else None,
        "shadow_rollout_enabled": shadow_rollout_enabled,
        "markov_rollout_enabled": settings.markov_rollout_enabled,
        "calibrated_forecast_enabled": settings.markov_rollout_enabled,
        "shadow_mode_enabled": shadow_rollout_enabled,
        "shadow_engine_kind": SHADOW_ENGINE_KIND if shadow_rollout_enabled else None,
        "shadow_execution_mode": SHADOW_EXECUTION_MODE if shadow_rollout_enabled else None,
        "shadow_bundle_version": SHADOW_BUNDLE_VERSION if shadow_rollout_enabled else None,
        "shadow_kpis": shadow_kpis or (list(SHADOW_SUPPORTED_KPIS) if shadow_rollout_enabled else []),
        "engine_kind": qualitative_engine_kind,
        "scored_kpis": [score.kpi_code for score in scored_kpis if score.value is not None],
        "event_count": len(events),
        "requirements_tracked": requirement_count,
        "sections_tracked": section_count,
    }


def compute_analysis_snapshot(tender: dict[str, Any] | None, events: list[dict[str, Any]], *, now: datetime | None = None) -> AnalysisSnapshot:
    if tender is None:
        return AnalysisSnapshot(
            analytical_phase=None,
            health="unknown",
            kpis=[],
            notes=["Tender not synchronized yet."],
            summary="Tender not synchronized yet.",
            analysis_metadata=_analysis_metadata(events=[], requirement_count=0, section_count=0, scored_kpis=[]),
        )

    now = now or datetime.now(timezone.utc)
    requirements = list(tender.get("requirement_contexts") or [])
    sections = list(tender.get("section_contexts") or [])
    current_status = _normalized(tender.get("current_status"))
    metadata = tender.get("metadata") or {}
    lifecycle = dict(metadata.get("lifecycle") or {})

    lifecycle_decision = _normalized((lifecycle.get("decision") or {}).get("decision")) or None
    lifecycle_outcome = _normalized((lifecycle.get("structured_outcome") or {}).get("outcome")) or None
    lifecycle_submission_status = _normalized((lifecycle.get("submission_status") or {}).get("submission_status")) or None
    lifecycle_clarification_active = any(
        _normalized(item.get("status")) not in {"closed", "resolved"}
        for item in list(lifecycle.get("clarifications") or [])
    )

    document_ingested = _count_events(events, "tender_document_ingested") > 0
    requirements_extracted = _count_events(events, "requirements_extracted") > 0
    proposal_updates = _count_events(events, "proposal_section_updated")
    submission_state = (
        lifecycle_submission_status
        or _latest_submission_state(events)
        or ("submitted" if current_status == "submitted" else None)
    )
    submitted = submission_state in {"submitted", "acknowledged"}
    submission_failed = submission_state == "failed"
    clarification_requested = _clarification_active(events) or lifecycle_clarification_active
    decision = _latest_decision(events) or lifecycle_decision
    bid_plan_started = (
        _count_events(events, "bid_plan_created") > 0
        or _count_events(events, "bid_plan_approved") > 0
        or bool(lifecycle.get("bid_plan"))
    )
    request_wave_opened = (
        _count_events(events, "contribution_request_wave_opened") > 0
        or _count_events(events, "contribution_assignment_confirmed") > 0
        or bool(lifecycle.get("contribution_wave"))
    )
    draft_ready = _count_events(events, "draft_integrated_ready") > 0 or bool(lifecycle.get("draft_ready"))
    outcome = _latest_outcome(events) or lifecycle_outcome

    requirement_count = len(requirements)
    addressed_requirements = sum(
        1
        for requirement in requirements
        if _normalized(requirement.get("compliance_status")) in _ADDRESSED_REQUIREMENT_STATUSES or bool(requirement.get("mapped_section_id"))
    )
    high_priority_requirements = sum(1 for requirement in requirements if _normalized(requirement.get("priority")) == "high")
    addressed_high_priority_requirements = sum(
        1
        for requirement in requirements
        if _normalized(requirement.get("priority")) == "high"
        and (_normalized(requirement.get("compliance_status")) in _ADDRESSED_REQUIREMENT_STATUSES or bool(requirement.get("mapped_section_id")))
    )
    active_sections = sum(1 for section in sections if _normalized(section.get("status")) in _ACTIVE_SECTION_STATUSES)
    completed_sections = sum(1 for section in sections if _normalized(section.get("status")) in _COMPLETED_SECTION_STATUSES)
    execution_started = (
        _count_events(events, "contribution_received") > 0
        or _count_events(events, "coordination_risk_raised") > 0
        or _count_events(events, "rework_reescalated_to_coordination") > 0
        or proposal_updates > 0
        or active_sections > 0
    )

    due_at = _parse_datetime(tender.get("due_at"))
    operational_state = _collect_operational_state(events)
    failed_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "failed")

    if document_ingested:
        proxy_a1 = _score_a1(
            requirement_count=requirement_count,
            addressed_requirements=addressed_requirements,
            section_count=len(sections),
            active_sections=active_sections,
            proposal_updates=proposal_updates,
            requirements_extracted=requirements_extracted,
        )
        proxy_a2 = _score_a2(
            document_ingested=document_ingested,
            sections=sections,
            requirement_count=requirement_count,
            addressed_requirements=addressed_requirements,
            completed_sections=completed_sections,
            proposal_updates=proposal_updates,
            operational_state=operational_state,
        )
        proxy_a3 = _score_a3(
            document_ingested=document_ingested,
            requirement_count=requirement_count,
            addressed_requirements=addressed_requirements,
            high_priority_requirements=high_priority_requirements,
            addressed_high_priority_requirements=addressed_high_priority_requirements,
            section_count=len(sections),
            completed_sections=completed_sections,
            proposal_updates=proposal_updates,
            operational_state=operational_state,
        )
        proxy_a4 = _score_a4(
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
        proxy_a1 = _unknown_score(
            kpi_code="A1",
            label="Requirement coverage becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document before computing requirement coverage.",
        )
        proxy_a2 = _unknown_score(
            kpi_code="A2",
            label="Editorial quality becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document before evaluating editorial quality.",
        )
        proxy_a3 = _unknown_score(
            kpi_code="A3",
            label="Competitive and technical value becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document before evaluating competitive and technical value.",
        )
        proxy_a4 = _unknown_score(
            kpi_code="A4",
            label="Compliance readiness becomes available after tender document ingestion.",
            evidence=["No `tender_document_ingested` event was observed yet."],
            recommendation="Ingest the tender document before evaluating compliance readiness.",
        )

    a1 = proxy_a1
    a2 = proxy_a2
    a3 = proxy_a3
    a4 = proxy_a4

    if settings.semantic_official_rollout_enabled:
        a1 = _with_semantic(
            proxy_a1,
            build_a1_semantic(
                requirements=requirements,
                document_ingested=document_ingested,
                requirements_extracted=requirements_extracted,
                proxy_score=proxy_a1.value,
            ),
        )
        a2 = _with_semantic(
            proxy_a2,
            build_a2_semantic(
                document_ingested=document_ingested,
                sections=sections,
                requirement_count=requirement_count,
                addressed_requirements=addressed_requirements,
                completed_sections=completed_sections,
                proposal_updates=proposal_updates,
                reviews_started=operational_state.reviews_started,
                reviews_completed=operational_state.reviews_completed,
                reworks=operational_state.reworks,
                proxy_score=proxy_a2.value,
            ),
        )
        a3 = _with_semantic(
            proxy_a3,
            build_a3_semantic(
                document_ingested=document_ingested,
                requirement_count=requirement_count,
                addressed_requirements=addressed_requirements,
                high_priority_requirements=high_priority_requirements,
                addressed_high_priority_requirements=addressed_high_priority_requirements,
                section_count=len(sections),
                completed_sections=completed_sections,
                proposal_updates=proposal_updates,
                requests=operational_state.requests,
                reviews_completed=operational_state.reviews_completed,
                reworks=operational_state.reworks,
                gates=operational_state.gates,
                proxy_score=proxy_a3.value,
            ),
        )
        a4 = _with_semantic(
            proxy_a4,
            build_a4_semantic(
                requirements=requirements,
                document_ingested=document_ingested,
                requirements_extracted=requirements_extracted,
                section_count=len(sections),
                active_sections=active_sections,
                due_at=due_at,
                now=now,
                submitted=submitted,
                failed_gates=failed_gates,
                proxy_score=proxy_a4.value,
            ),
        )
    elif settings.semantic_shadow_rollout_enabled:
        a1 = _with_shadow(
            proxy_a1,
            build_a1_shadow(
                requirements=requirements,
                document_ingested=document_ingested,
                requirements_extracted=requirements_extracted,
                proxy_score=proxy_a1.value,
            ),
        )
        a4 = _with_shadow(
            proxy_a4,
            build_a4_shadow(
                requirements=requirements,
                document_ingested=document_ingested,
                requirements_extracted=requirements_extracted,
                section_count=len(sections),
                active_sections=active_sections,
                due_at=due_at,
                now=now,
                submitted=submitted,
                failed_gates=failed_gates,
                proxy_score=proxy_a4.value,
            ),
        )

    q = _score_q([a1, a2, a3, a4])
    if settings.semantic_official_rollout_enabled:
        q = _with_qualitative_summary_contract(q)

    operational = _compute_operational_snapshot(events, now, state=operational_state)
    failed_gates = sum(1 for gate in operational_state.gates if _normalized(gate.get("status")) == "failed")
    all_scores = [a1, a2, a3, a4, q, operational.b1, operational.b2, operational.b3, operational.b4, operational.e]
    health = _derive_health(scores=all_scores, q_score=q, e_score=operational.e, a4_score=a4, failed_gates=failed_gates)
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
        submission_failed=submission_failed,
        clarification_requested=clarification_requested,
        decision=decision,
        bid_plan_started=bid_plan_started,
        request_wave_opened=request_wave_opened,
        draft_ready=draft_ready,
        execution_started=execution_started,
        operational_state=operational_state,
    )

    semantic_note = (
        "Official semantic scoring is active for A1..A4; Q and tender health now use the semantic layer with proxy scores retained for comparison."
        if settings.semantic_official_rollout_enabled
        else (
            "Semantic shadow mode is active for A1 and A4; official Q and tender health still use proxy scores."
            if settings.semantic_shadow_rollout_enabled
            else f"Semantic official scoring is disabled by rollout policy {settings.normalized_rollout_policy}; official Q and tender health use proxy scores only."
        )
    )
    notes = [
        f"Requirements tracked in mirror: {requirement_count}.",
        f"Proposal sections tracked in mirror: {len(sections)} ({completed_sections} completed).",
        f"Observed `proposal_section_updated` events: {proposal_updates}.",
        semantic_note,
        *(["Post-submission clarifications are active in telemetry."] if clarification_requested else []),
        *([f"Failed compliance gates observed: {failed_gates}."] if failed_gates else []),
        *operational.notes,
    ]

    if not document_ingested:
        summary = "Tender mirror is available, but the tender document has not been ingested yet."
    elif requirement_count == 0:
        summary = "Tender document ingestion exists, but extracted requirements are still missing or empty."
    elif settings.semantic_official_rollout_enabled and any(score.value is not None for score in [operational.b1, operational.b2, operational.b3, operational.b4]):
        summary = "Analytical snapshot is available with official semantic A1..A4/Q plus B1..B4/E from observed workflow telemetry."
    elif settings.semantic_official_rollout_enabled:
        summary = "Analytical snapshot is available with official semantic A1..A4/Q and base tender telemetry."
    elif any(score.value is not None for score in [operational.b1, operational.b2, operational.b3, operational.b4]):
        summary = "Analytical snapshot is available for A1..A4, Q and B1..B4/E using persisted requirements, proposal progress and observed workflow telemetry."
    else:
        summary = "Analytical snapshot is available for A1..A4 and Q using persisted requirements, proposal progress and base tender telemetry."

    return AnalysisSnapshot(
        analytical_phase=analytical_phase,
        health=health,
        kpis=all_scores,
        notes=notes,
        summary=summary,
        analysis_metadata=_analysis_metadata(events=events, requirement_count=requirement_count, section_count=len(sections), scored_kpis=all_scores),
    )
