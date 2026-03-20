"""Deterministic semantic shadow helpers for Sprint 15 side-by-side A1/A4 evaluation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.contract import (
    AMBER_Q_THRESHOLD,
    GREEN_A4_THRESHOLD,
    SHADOW_ENGINE_KIND,
    SHADOW_EXECUTION_MODE,
    SHADOW_FORMULA_VERSIONS,
    SHADOW_MODEL_VERSION,
    SHADOW_PROMPT_VERSION,
    normalize_source_type,
)
from app.schemas import HealthClass, SemanticCoverageGap, SemanticRiskItem, SemanticShadowEvaluation

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


def _days_until(due_at: datetime | None, now: datetime) -> float | None:
    if due_at is None:
        return None
    return (due_at - now).total_seconds() / 86400


def _shadow_base(*, kpi_code: str, proxy_score: float | None) -> dict[str, Any]:
    return {
        "enabled": True,
        "engine_kind": SHADOW_ENGINE_KIND,
        "execution_mode": SHADOW_EXECUTION_MODE,
        "proxy_score": proxy_score,
        "formula_version": SHADOW_FORMULA_VERSIONS[kpi_code],
        "model_version": SHADOW_MODEL_VERSION,
        "prompt_version": SHADOW_PROMPT_VERSION,
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


def build_a1_shadow(
    *,
    requirements: list[dict[str, Any]],
    document_ingested: bool,
    requirements_extracted: bool,
    proxy_score: float | None,
) -> SemanticShadowEvaluation:
    base = _shadow_base(kpi_code="A1", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticShadowEvaluation(
            **base,
            shadow_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic shadow is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document before comparing semantic A1 against the proxy score."],
        )

    requirement_count = len(requirements)
    if requirement_count == 0:
        return SemanticShadowEvaluation(
            **base,
            shadow_score=0.0,
            health="red",
            confidence=0.58,
            source_type="inferred",
            evidences=["Semantic shadow cannot score A1 because no requirement baseline is available."],
            criticalities=["No extracted requirements are available for semantic coverage review."],
            recommendations=["Restore the requirement baseline before using semantic A1 as a readiness signal."],
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
    shadow_score = round(min(1.0, (weighted_coverage * 0.85) + (mapping_ratio * 0.15)) * 100, 1)
    health = _health_from_score(shadow_score, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    confidence = 0.52
    if requirements_extracted:
        confidence += 0.16
    confidence += 0.07 if described_requirements == requirement_count else (0.03 if described_requirements else 0.0)
    confidence += 0.07 if explicit_statuses == requirement_count else (0.04 if explicit_statuses else 0.0)
    confidence = round(min(0.84, confidence), 2)

    criticalities: list[str] = []
    missing_count = sum(1 for item in coverage_gaps if item.status in {"missing", "mapped_only"})
    partial_count = sum(1 for item in coverage_gaps if item.status == "partial")
    if missing_high_priority:
        criticalities.append(f"{missing_high_priority} high-priority requirement still lacks solid semantic coverage.")
    if missing_count:
        criticalities.append(f"{missing_count} requirement still lacks substantive coverage in the semantic shadow review.")
    if partial_count:
        criticalities.append(f"{partial_count} requirement is only partially addressed in the semantic shadow review.")

    if health == "green":
        recommendations = ["Keep semantic requirement evidence aligned with the current section mapping and preserve traceability."]
    elif health == "amber":
        recommendations = ["Convert mapped-only and partial requirements into explicit substantive coverage before the next gate."]
    else:
        recommendations = ["Close the missing requirement coverage before using A1 shadow as a readiness signal."]

    source_type = normalize_source_type("observed" if requirements_extracted and explicit_statuses > 0 else "inferred")
    evidences = [
        f"Semantic full coverage: {fully_addressed}/{requirement_count}.",
        f"Semantic partial or mapped-only coverage: {partially_addressed + mapped_only}/{requirement_count}.",
        f"Requirements with section mapping: {mapped_count}/{requirement_count}.",
        f"Semantic coverage gaps surfaced: {len(coverage_gaps)}.",
    ]
    return SemanticShadowEvaluation(
        **base,
        shadow_score=shadow_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=evidences,
        criticalities=criticalities,
        recommendations=recommendations,
        coverage_gaps=coverage_gaps,
    )


def build_a4_shadow(
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
) -> SemanticShadowEvaluation:
    base = _shadow_base(kpi_code="A4", proxy_score=proxy_score)
    if not document_ingested:
        return SemanticShadowEvaluation(
            **base,
            shadow_score=None,
            health="unknown",
            confidence=0.0,
            source_type="unknown",
            evidences=["Semantic shadow is waiting for tender document ingestion."],
            recommendations=["Ingest the tender document before comparing semantic A4 against the proxy score."],
        )

    requirement_count = len(requirements)
    if requirement_count == 0:
        return SemanticShadowEvaluation(
            **base,
            shadow_score=0.0,
            health="red",
            confidence=0.58,
            source_type="inferred",
            evidences=["Semantic shadow cannot score A4 because no requirement baseline is available."],
            criticalities=["No extracted requirements are available for semantic compliance review."],
            recommendations=["Restore the requirement baseline before using semantic A4 as a compliance signal."],
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
            evidence="Due date pressure is part of the semantic compliance shadow signal.",
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
    shadow_score = round(max(0.0, 100.0 - risk_total), 1)
    health = _health_from_score(shadow_score, green=GREEN_A4_THRESHOLD, amber=AMBER_Q_THRESHOLD)

    confidence = 0.54
    if requirements_extracted:
        confidence += 0.12
    if due_at is not None:
        confidence += 0.08
    if section_count > 0:
        confidence += 0.06
    if explicit_statuses > 0:
        confidence += 0.05
    confidence = round(min(0.82, confidence), 2)

    criticalities = [item.summary for item in risk_items if item.severity in {"high", "critical"}][:3]
    if health == "green":
        recommendations = ["Maintain the current semantic compliance evidence and keep the deadline buffer under control."]
    elif health == "amber":
        recommendations = ["Reduce semantic requirement gaps and deadline pressure before the next compliance decision."]
    else:
        recommendations = ["Escalate unresolved semantic compliance gaps immediately; A4 shadow is not yet ready for progression."]

    source_type = normalize_source_type("observed" if requirements_extracted and due_at is not None and explicit_statuses > 0 else "inferred")
    evidences = [
        f"Semantic unresolved requirements: {unresolved_requirements}/{requirement_count}.",
        f"Semantic unresolved high-priority requirements: {unresolved_high_priority}.",
        due_summary,
        f"Failed compliance gates reflected in shadow: {failed_gates}.",
    ]
    return SemanticShadowEvaluation(
        **base,
        shadow_score=shadow_score,
        health=health,
        confidence=confidence,
        source_type=source_type,
        evidences=evidences,
        criticalities=criticalities,
        recommendations=recommendations,
        risk_items=risk_items,
    )
