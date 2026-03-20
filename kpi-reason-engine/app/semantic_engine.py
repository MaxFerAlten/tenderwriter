"""Deterministic semantic evaluation helpers for Sprint 19 official qualitative scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contract import (
    AMBER_Q_THRESHOLD,
    GREEN_A4_THRESHOLD,
    GREEN_Q_THRESHOLD,
    SEMANTIC_ENGINE_KIND,
    SEMANTIC_EXECUTION_MODE,
    SEMANTIC_FORMULA_VERSIONS,
    SEMANTIC_MODEL_VERSION,
    SEMANTIC_PROMPT_VERSION,
    normalize_source_type,
)
from app.schemas import (
    HealthClass,
    SemanticCoverageGap,
    SemanticDimensionItem,
    SemanticEvaluation,
    SemanticRiskItem,
)

_FULLY_ADDRESSED = {"fully_addressed"}
_PARTIALLY_ADDRESSED = {"partially_addressed"}


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


def _severity_from_ratio(value: float) -> str:
    if value >= 0.8:
        return "low"
    if value >= 0.6:
        return "medium"
    if value >= 0.4:
        return "high"
    return "critical"


def _days_until(due_at: datetime | None, now: datetime) -> float | None:
    if due_at is None:
        return None
    return (due_at - now).total_seconds() / 86400


def _semantic_base(*, kpi_code: str, proxy_score: float | None) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "official",
        "engine_kind": SEMANTIC_ENGINE_KIND,
        "execution_mode": SEMANTIC_EXECUTION_MODE,
        "proxy_score": proxy_score,
        "formula_version": SEMANTIC_FORMULA_VERSIONS[kpi_code],
        "model_version": SEMANTIC_MODEL_VERSION,
        "prompt_version": SEMANTIC_PROMPT_VERSION,
    }


def _gap(requirement: dict[str, Any], *, status: str) -> SemanticCoverageGap:
    return SemanticCoverageGap(
        external_requirement_id=str(requirement.get("external_requirement_id") or "unknown"),
        reference=requirement.get("reference"),
        summary=requirement.get("summary"),
        priority=requirement.get("priority"),
        status=status,
        mapped_section_id=requirement.get("mapped_section_id"),
    )


def build_a1_semantic(
    *,
    requirements: list[dict[str, Any]],
    document_ingested: bool,
    requirements_extracted: bool,
    proxy_score: float | None,
) -> SemanticEvaluation:
    base = _semantic_base(kpi_code="A1", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticEvaluation(
            **base,
            semantic_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic A1 is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document before running official semantic requirement coverage."],
        )

    requirement_count = len(requirements)
    if requirement_count == 0:
        return SemanticEvaluation(
            **base,
            semantic_score=0.0,
            health="red",
            confidence=0.6,
            source_type="inferred",
            evidences=["Semantic A1 cannot score because no extracted requirement baseline is available."],
            criticalities=["No extracted requirements are available for official semantic coverage review."],
            recommendations=["Restore the requirement baseline before using semantic A1 as an official score."],
        )

    fully_addressed = 0
    partially_addressed = 0
    mapped_only = 0
    mapped_count = 0
    explicit_statuses = 0
    described_requirements = 0
    missing_high_priority = 0
    coverage_gaps: list[SemanticCoverageGap] = []

    for requirement in requirements:
        status = _normalized(requirement.get("compliance_status"))
        priority = _normalized(requirement.get("priority"))
        mapped = bool(requirement.get("mapped_section_id"))
        if mapped:
            mapped_count += 1
        if requirement.get("summary"):
            described_requirements += 1
        if status:
            explicit_statuses += 1

        if status in _FULLY_ADDRESSED:
            fully_addressed += 1
            continue
        if status in _PARTIALLY_ADDRESSED:
            partially_addressed += 1
            coverage_gaps.append(_gap(requirement, status="partial"))
            if priority == "high":
                missing_high_priority += 1
            continue
        if mapped:
            mapped_only += 1
            coverage_gaps.append(_gap(requirement, status="mapped_only"))
            if priority == "high":
                missing_high_priority += 1
            continue
        coverage_gaps.append(_gap(requirement, status="missing"))
        if priority == "high":
            missing_high_priority += 1

    weighted_coverage = (fully_addressed + (partially_addressed * 0.60) + (mapped_only * 0.25)) / requirement_count
    mapping_ratio = mapped_count / requirement_count
    semantic_score = round(min(1.0, (weighted_coverage * 0.85) + (mapping_ratio * 0.15)) * 100, 1)
    health = _health_from_score(semantic_score, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    confidence = 0.58
    if requirements_extracted:
        confidence += 0.14
    confidence += 0.06 if described_requirements == requirement_count else (0.03 if described_requirements else 0.0)
    confidence += 0.06 if explicit_statuses == requirement_count else (0.03 if explicit_statuses else 0.0)
    confidence = round(min(0.86, confidence), 2)

    dimension_items = [
        SemanticDimensionItem(
            code="substantive_coverage",
            severity=_severity_from_ratio(weighted_coverage),
            summary=f"Substantive semantic coverage sits at {round(weighted_coverage * 100, 1)}%.",
            evidence=f"Fully addressed: {fully_addressed}; partial or mapped-only: {partially_addressed + mapped_only}; total: {requirement_count}.",
        ),
        SemanticDimensionItem(
            code="traceability",
            severity=_severity_from_ratio(mapping_ratio),
            summary=f"Requirement-to-section traceability sits at {round(mapping_ratio * 100, 1)}%.",
            evidence=f"Mapped requirements: {mapped_count}/{requirement_count}.",
        ),
    ]

    criticalities: list[str] = []
    missing_count = sum(1 for item in coverage_gaps if item.status in {"missing", "mapped_only"})
    partial_count = sum(1 for item in coverage_gaps if item.status == "partial")
    if missing_high_priority:
        criticalities.append(f"{missing_high_priority} high-priority requirement still lacks solid semantic coverage.")
    if missing_count:
        criticalities.append(f"{missing_count} requirement still lacks substantive coverage in the official semantic review.")
    if partial_count:
        criticalities.append(f"{partial_count} requirement is only partially addressed in the official semantic review.")

    if health == "green":
        recommendations = ["Keep semantic requirement evidence aligned with section mapping and preserve traceability into the final gate."]
    elif health == "amber":
        recommendations = ["Convert mapped-only and partial requirements into explicit substantive coverage before the next compliance decision."]
    else:
        recommendations = ["Close the missing requirement coverage before using A1 as an official readiness signal."]

    source_type = normalize_source_type("observed" if requirements_extracted and explicit_statuses > 0 else "inferred")
    evidences = [
        f"Semantic full coverage: {fully_addressed}/{requirement_count}.",
        f"Semantic partial or mapped-only coverage: {partially_addressed + mapped_only}/{requirement_count}.",
        f"Requirements with section mapping: {mapped_count}/{requirement_count}.",
        f"Semantic coverage gaps surfaced: {len(coverage_gaps)}.",
    ]
    return SemanticEvaluation(
        **base,
        semantic_score=semantic_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=evidences,
        criticalities=criticalities,
        recommendations=recommendations,
        coverage_gaps=coverage_gaps,
        dimension_items=dimension_items,
    )


def build_a2_semantic(
    *,
    document_ingested: bool,
    sections: list[dict[str, Any]],
    requirement_count: int,
    addressed_requirements: int,
    completed_sections: int,
    proposal_updates: int,
    reviews_started: int,
    reviews_completed: int,
    reworks: list[dict[str, Any]],
    proxy_score: float | None,
) -> SemanticEvaluation:
    base = _semantic_base(kpi_code="A2", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticEvaluation(
            **base,
            semantic_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic A2 is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document and sync sections before evaluating editorial quality."],
        )

    section_count = len(sections)
    if section_count == 0:
        return SemanticEvaluation(
            **base,
            semantic_score=0.0,
            health="red",
            confidence=0.56,
            source_type="inferred",
            evidences=["Semantic A2 cannot score because no proposal sections are tracked yet."],
            criticalities=["No proposal sections are available for editorial review."],
            recommendations=["Create the proposal structure before using semantic A2 as an official quality score."],
        )

    meaningful_titles = sum(1 for section in sections if len(str(section.get("title") or "").strip()) >= 8)
    title_quality_ratio = meaningful_titles / section_count
    progress_ratio = completed_sections / section_count if section_count else 0.0
    review_closure_ratio = (
        reviews_completed / reviews_started
        if reviews_started
        else (0.65 if completed_sections > 0 else 0.25)
    )
    open_reworks = sum(1 for rework in reworks if rework.get("resolved_at") is None)
    rework_penalty = min((open_reworks + (len(reworks) * 0.35)) / max(1, section_count), 1.0)
    alignment_ratio = addressed_requirements / requirement_count if requirement_count else min(section_count / 3.0, 1.0)
    update_ratio = min(proposal_updates / max(1, section_count), 1.0)

    semantic_score = round(
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
    health = _health_from_score(semantic_score, green=GREEN_Q_THRESHOLD, amber=AMBER_Q_THRESHOLD)
    source_type = normalize_source_type("observed" if reviews_started or reworks else "inferred")
    confidence = 0.68
    if reviews_started:
        confidence += 0.08
    if proposal_updates:
        confidence += 0.05
    if requirement_count:
        confidence += 0.04
    confidence = round(min(0.86, confidence), 2)

    dimension_items = [
        SemanticDimensionItem(
            code="structure_quality",
            severity=_severity_from_ratio(title_quality_ratio),
            summary=f"Section naming and structure quality sit at {round(title_quality_ratio * 100, 1)}%.",
            evidence=f"Meaningful section titles: {meaningful_titles}/{section_count}.",
        ),
        SemanticDimensionItem(
            code="review_maturity",
            severity=_severity_from_ratio(review_closure_ratio),
            summary=f"Editorial review maturity sits at {round(review_closure_ratio * 100, 1)}%.",
            evidence=f"Review cycles started/completed: {reviews_started}/{reviews_completed}.",
        ),
        SemanticDimensionItem(
            code="stability_under_revision",
            severity=_severity_from_ratio(1.0 - rework_penalty),
            summary=f"Narrative stability under revision sits at {round((1.0 - rework_penalty) * 100, 1)}%.",
            evidence=f"Open rework loops: {open_reworks}; total reworks: {len(reworks)}.",
        ),
        SemanticDimensionItem(
            code="requirement_alignment",
            severity=_severity_from_ratio(alignment_ratio),
            summary=f"Narrative alignment with requirement coverage sits at {round(alignment_ratio * 100, 1)}%.",
            evidence=f"Addressed requirements: {addressed_requirements}/{requirement_count or section_count}.",
        ),
    ]

    criticalities: list[str] = []
    if open_reworks > 0:
        criticalities.append(f"{open_reworks} open rework loop still degrades editorial consistency.")
    if review_closure_ratio < 0.6:
        criticalities.append("Review closure is still too weak to support strong editorial confidence.")
    if title_quality_ratio < 0.6:
        criticalities.append("Several section titles remain too weak to communicate a clear narrative structure.")

    if open_reworks > 0:
        recommendations = ["Resolve open rework loops and stabilize the latest section revisions before claiming editorial readiness."]
    elif health == "green":
        recommendations = ["Maintain the current editorial cadence and preserve section consistency through the final integration pass."]
    elif health == "amber":
        recommendations = ["Tighten wording, complete the pending reviews and push more sections into approved state."]
    else:
        recommendations = ["Formalize the proposal structure and start disciplined reviews before using A2 as a quality signal."]

    return SemanticEvaluation(
        **base,
        semantic_score=semantic_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=[
            f"Proposal sections tracked: {section_count}, with {completed_sections} completed.",
            f"Sections with meaningful titles: {meaningful_titles}/{section_count}.",
            f"Review cycles started/completed: {reviews_started}/{reviews_completed}.",
            f"Open rework loops: {open_reworks}; proposal section updates observed: {proposal_updates}.",
        ],
        criticalities=criticalities,
        recommendations=recommendations,
        dimension_items=dimension_items,
    )


def build_a3_semantic(
    *,
    document_ingested: bool,
    requirement_count: int,
    addressed_requirements: int,
    high_priority_requirements: int,
    addressed_high_priority_requirements: int,
    section_count: int,
    completed_sections: int,
    proposal_updates: int,
    requests: list[dict[str, Any]],
    reviews_completed: int,
    reworks: list[dict[str, Any]],
    gates: list[dict[str, Any]],
    proxy_score: float | None,
) -> SemanticEvaluation:
    base = _semantic_base(kpi_code="A3", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticEvaluation(
            **base,
            semantic_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic A3 is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document and establish requirement coverage before evaluating competitive value."],
        )

    if requirement_count == 0:
        return SemanticEvaluation(
            **base,
            semantic_score=0.0,
            health="red",
            confidence=0.56,
            source_type="inferred",
            evidences=["Semantic A3 cannot score because no requirement baseline is available."],
            criticalities=["No persisted requirements are available to assess technical positioning."],
            recommendations=["Recover the requirement baseline before using semantic A3 as an official score."],
        )

    high_priority_focus = (
        addressed_high_priority_requirements / high_priority_requirements
        if high_priority_requirements
        else addressed_requirements / requirement_count
    )
    delivery_depth = completed_sections / section_count if section_count else 0.0
    open_blocking_reworks = sum(
        1 for rework in reworks if rework.get("is_blocking") and rework.get("resolved_at") is None
    )
    failed_gates = sum(1 for gate in gates if _normalized(gate.get("status")) == "failed")
    open_gates = sum(1 for gate in gates if _normalized(gate.get("status")) == "open")
    blocker_ratio = min(
        ((open_blocking_reworks * 1.0) + (failed_gates * 1.0) + (open_gates * 0.6))
        / max(1, high_priority_requirements or requirement_count),
        1.0,
    )
    review_depth = min((reviews_completed + proposal_updates) / max(1, requirement_count), 1.0)
    request_coverage = min(len(requests) / max(1, section_count or requirement_count), 1.0)

    semantic_score = round(
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
    health = _health_from_score(semantic_score, green=GREEN_Q_THRESHOLD, amber=AMBER_Q_THRESHOLD)
    source_type = normalize_source_type("observed" if (gates or reworks or reviews_completed or requests) else "inferred")
    confidence = 0.7
    if gates or reworks:
        confidence += 0.08
    if reviews_completed:
        confidence += 0.05
    if requests:
        confidence += 0.03
    confidence = round(min(0.86, confidence), 2)

    dimension_items = [
        SemanticDimensionItem(
            code="priority_fit",
            severity=_severity_from_ratio(high_priority_focus),
            summary=f"High-priority requirement fit sits at {round(high_priority_focus * 100, 1)}%.",
            evidence=f"High-priority requirements addressed: {addressed_high_priority_requirements}/{high_priority_requirements or requirement_count}.",
        ),
        SemanticDimensionItem(
            code="delivery_depth",
            severity=_severity_from_ratio(delivery_depth),
            summary=f"Delivery depth of the proposal sits at {round(delivery_depth * 100, 1)}%.",
            evidence=f"Completed sections: {completed_sections}/{section_count or 0}.",
        ),
        SemanticDimensionItem(
            code="blocker_pressure",
            severity=_severity_from_ratio(1.0 - blocker_ratio),
            summary=f"Blocker resilience sits at {round((1.0 - blocker_ratio) * 100, 1)}%.",
            evidence=f"Blocking rework open: {open_blocking_reworks}; open/failed gates: {open_gates}/{failed_gates}.",
        ),
        SemanticDimensionItem(
            code="validation_depth",
            severity=_severity_from_ratio(review_depth),
            summary=f"Validation depth sits at {round(review_depth * 100, 1)}%.",
            evidence=f"Review completions plus section updates observed: {reviews_completed + proposal_updates}.",
        ),
    ]

    criticalities: list[str] = []
    if open_blocking_reworks > 0:
        criticalities.append("Blocking rework is still weakening the technical positioning of the offer.")
    if failed_gates > 0:
        criticalities.append("Failed compliance gates still undermine the credibility of the proposed solution.")
    if high_priority_focus < 0.65:
        criticalities.append("High-priority requirements are not yet covered strongly enough to claim competitive value.")

    if open_blocking_reworks > 0 or failed_gates > 0:
        recommendations = ["Close blocking rework and failed gates on high-priority requirements before presenting the offer as competitive."]
    elif health == "green":
        recommendations = ["Protect the current technical positioning by keeping high-priority requirements fully covered through submission."]
    elif health == "amber":
        recommendations = ["Increase coverage on the highest-priority requirements and complete more sections to strengthen offer value."]
    else:
        recommendations = ["Refocus the proposal on the highest-priority requirements and remove unresolved blockers that weaken technical credibility."]

    return SemanticEvaluation(
        **base,
        semantic_score=semantic_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=[
            f"High-priority requirements addressed: {addressed_high_priority_requirements}/{high_priority_requirements or requirement_count}.",
            f"Completed proposal sections: {completed_sections}/{section_count or 0}.",
            f"Blocking rework open: {open_blocking_reworks}; open/failed gates: {open_gates}/{failed_gates}.",
            f"Review completions plus section updates observed: {reviews_completed + proposal_updates}.",
        ],
        criticalities=criticalities,
        recommendations=recommendations,
        dimension_items=dimension_items,
    )


def build_a4_semantic(
    *,
    requirements: list[dict[str, Any]],
    document_ingested: bool,
    requirements_extracted: bool,
    section_count: int,
    active_sections: int,
    due_at: datetime | None,
    now: datetime,
    submitted: bool,
    failed_gates: int,
    proxy_score: float | None,
) -> SemanticEvaluation:
    base = _semantic_base(kpi_code="A4", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticEvaluation(
            **base,
            semantic_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic A4 is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document before evaluating official semantic compliance readiness."],
        )

    requirement_count = len(requirements)
    if requirement_count == 0:
        return SemanticEvaluation(
            **base,
            semantic_score=0.0,
            health="red",
            confidence=0.6,
            source_type="inferred",
            evidences=["Semantic A4 cannot score because no extracted requirement baseline is available."],
            criticalities=["No extracted requirements are available for official semantic compliance review."],
            recommendations=["Restore the requirement baseline before using semantic A4 as an official compliance score."],
        )

    requirement_penalty_total = 0.0
    unresolved_requirements = 0
    unresolved_high_priority = 0
    explicit_statuses = 0
    risk_items: list[SemanticRiskItem] = []

    for requirement in requirements:
        status = _normalized(requirement.get("compliance_status"))
        priority = _normalized(requirement.get("priority"))
        mapped = bool(requirement.get("mapped_section_id"))
        if status:
            explicit_statuses += 1
        if status in _FULLY_ADDRESSED:
            continue

        unresolved_requirements += 1
        if priority == "high":
            unresolved_high_priority += 1

        if status in _PARTIALLY_ADDRESSED:
            penalty = 20 if priority == "high" else 14
            severity = "high" if priority == "high" else "medium"
            summary = "Partially addressed requirement still carries semantic compliance risk."
        elif mapped:
            penalty = 24 if priority == "high" else 18
            severity = "high" if priority == "high" else "medium"
            summary = "Requirement is mapped but still lacks substantive semantic coverage."
        else:
            penalty = 30 if priority == "high" else 20
            severity = "critical" if priority == "high" else "high"
            summary = "Requirement is still uncovered in the semantic compliance review."

        requirement_penalty_total += penalty
        risk_items.append(
            SemanticRiskItem(
                code="requirement_gap",
                severity=severity,
                summary=summary,
                related_requirement_id=requirement.get("external_requirement_id"),
                evidence=requirement.get("summary") or requirement.get("reference"),
            )
        )

    due_days = _days_until(due_at, now)
    if due_days is None:
        due_penalty = 12.0
        due_summary = "Tender deadline is missing from the synchronized mirror."
        due_severity = "medium"
    elif due_days < 0:
        due_penalty = 35.0
        due_summary = f"Tender deadline already passed {abs(round(due_days, 1))} days ago."
        due_severity = "critical"
    elif due_days <= 3:
        due_penalty = 28.0
        due_summary = f"Tender deadline is in {round(due_days, 1)} days."
        due_severity = "critical"
    elif due_days <= 7:
        due_penalty = 20.0
        due_summary = f"Tender deadline is in {round(due_days, 1)} days."
        due_severity = "high"
    elif due_days <= 14:
        due_penalty = 12.0
        due_summary = f"Tender deadline is in {round(due_days, 1)} days."
        due_severity = "medium"
    else:
        due_penalty = 8.0
        due_summary = f"Tender deadline is in {round(due_days, 1)} days."
        due_severity = "low"

    risk_items.append(
        SemanticRiskItem(
            code="deadline_window",
            severity=due_severity,
            summary=due_summary,
            evidence="Due date pressure is part of the official semantic compliance signal.",
        )
    )

    gate_penalty = float(failed_gates * 18)
    if failed_gates:
        risk_items.append(
            SemanticRiskItem(
                code="failed_gate",
                severity="critical",
                summary=f"{failed_gates} failed compliance gate(s) are still reflected in telemetry.",
                evidence="Failed gates remain a decisive semantic readiness blocker.",
            )
        )

    section_penalty = 10.0 if section_count == 0 else (5.0 if active_sections == 0 and not submitted else 0.0)
    if section_penalty:
        risk_items.append(
            SemanticRiskItem(
                code="section_readiness",
                severity="medium",
                summary="Proposal section readiness is still weak for semantic compliance review.",
                evidence=f"Tracked sections: {section_count}, active sections: {active_sections}.",
            )
        )

    requirement_risk = requirement_penalty_total / requirement_count
    risk_total = min(100.0, requirement_risk + due_penalty + gate_penalty + section_penalty)
    if submitted:
        risk_total = max(0.0, risk_total - 4.0)
    semantic_score = round(max(0.0, 100.0 - risk_total), 1)
    health = _health_from_score(semantic_score, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    confidence = 0.58
    if requirements_extracted:
        confidence += 0.12
    if due_at is not None:
        confidence += 0.08
    if section_count > 0:
        confidence += 0.05
    if explicit_statuses > 0:
        confidence += 0.05
    confidence = round(min(0.84, confidence), 2)

    dimension_items = [
        SemanticDimensionItem(
            code="requirement_risk",
            severity=_severity_from_ratio(max(0.0, 1.0 - (requirement_risk / 30.0))),
            summary=f"Requirement risk pressure is {round(requirement_risk, 1)} points over the semantic compliance baseline.",
            evidence=f"Unresolved requirements: {unresolved_requirements}/{requirement_count}; high-priority unresolved: {unresolved_high_priority}.",
        ),
        SemanticDimensionItem(
            code="deadline_pressure",
            severity=due_severity,
            summary=due_summary,
            evidence="Deadline proximity materially influences compliance readiness.",
        ),
    ]

    criticalities = [item.summary for item in risk_items if item.severity in {"high", "critical"}][:4]
    if health == "green":
        recommendations = ["Maintain the current semantic compliance evidence and keep the deadline buffer under control."]
    elif health == "amber":
        recommendations = ["Reduce semantic requirement gaps and deadline pressure before the next compliance decision."]
    else:
        recommendations = ["Escalate unresolved semantic compliance gaps immediately; A4 is not yet ready for progression."]

    source_type = normalize_source_type("observed" if requirements_extracted and due_at is not None and explicit_statuses > 0 else "inferred")
    evidences = [
        f"Semantic unresolved requirements: {unresolved_requirements}/{requirement_count}.",
        f"Semantic unresolved high-priority requirements: {unresolved_high_priority}.",
        due_summary,
        f"Failed compliance gates reflected in semantic scoring: {failed_gates}.",
    ]
    return SemanticEvaluation(
        **base,
        semantic_score=semantic_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=evidences,
        criticalities=criticalities,
        recommendations=recommendations,
        risk_items=risk_items,
        dimension_items=dimension_items,
    )
