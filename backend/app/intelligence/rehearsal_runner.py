"""Deterministic persona-evaluation loop over Wave-1 / Wave-2 tool outputs.

The runner is intentionally **LLM-free**.  It filters the already-computed
outputs of the intelligence tools by the persona's ``focus_domains`` and
folds them into a score, a list of findings, and a list of questions
using the persona's own ``scoring_weights``.

This keeps the rehearsal grounded (findings are always backed by tool
outputs that already exist) and cheap to run (no extra LLM calls on top
of the Wave-1/2 evaluations).

The rubric for the score is deliberately simple:

    score = 100
          − mandatory_coverage_weight * uncovered_high_priority_penalty
          − evidence_depth_weight    * missing_evidence_penalty
          − formal_consistency_weight * contradiction_penalty
          − compliance_weight        * (failed_gate + blocking_rework) penalty

Per-persona weights decide which dimension matters most.  A persona
without a weight for a dimension is insensitive to it — this is what
separates ``formalista_amministrativo`` from ``valutatore_tecnico``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.intelligence.personas import ReviewerPersona

# ------------------------------------------------------------------ Scoring

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

_BASE_SCORE = 100.0

# How much one unit of a penalty bucket costs under a 100% weight.  These
# are tuned so that a single blocking finding can not silently bring a
# score below zero while a handful of partially-covered requirements
# still move the needle.
_PENALTY_UNIT: dict[str, float] = {
    "mandatory_coverage": 12.0,
    "evidence_depth": 10.0,
    "formal_consistency": 12.0,
    "regulatory_coverage": 12.0,
    "certifications_presence": 10.0,
    "contradiction_absence": 15.0,
    "financial_sustainability": 12.0,
    "claim_credibility": 10.0,
    "guarantees_coverage": 10.0,
    "overall_readiness": 12.0,
    "blocking_risk_absence": 15.0,
    "package_reliability": 10.0,
    "technical_strength": 12.0,
    "service_levels": 10.0,
    "delivery_feasibility": 10.0,
    "innovation": 6.0,
}


# ------------------------------------------------------------------ Results


@dataclass(slots=True)
class PersonaEvaluation:
    """Deterministic evaluation of the tool outputs for a single persona."""

    persona_id: str
    display_name: str
    reviewer_type: str
    score: float
    findings: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    metrics: dict[str, Any]


# ------------------------------------------------------------------ Helpers


def _normalise_domain(domain: Any) -> str | None:
    if domain is None:
        return None
    return str(domain).casefold().strip() or None


def _persona_focus_set(persona: ReviewerPersona) -> set[str]:
    return {d.casefold() for d in persona.focus_domains}


def _matches_focus(persona_domains: set[str], domain: Any) -> bool:
    if not persona_domains:
        return True
    normalised = _normalise_domain(domain)
    if normalised is None:
        return True
    return normalised in persona_domains


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _coerce_severity(
    raw: Any,
    *,
    default: str = "medium",
) -> str:
    value = (raw or default).casefold() if isinstance(raw, str) else default
    return value if value in _SEVERITY_ORDER else default


# ------------------------------------------------------------------ Filters


def _filter_coverage_gaps(
    coverage: Mapping[str, Any],
    persona: ReviewerPersona,
) -> list[dict[str, Any]]:
    focus = _persona_focus_set(persona)
    return [
        gap
        for gap in _as_list(coverage.get("gaps"))
        if isinstance(gap, Mapping) and _matches_focus(focus, gap.get("ontology_domain"))
    ]


def _filter_evidence_findings(
    evidence: Mapping[str, Any],
    persona: ReviewerPersona,
) -> list[dict[str, Any]]:
    focus = _persona_focus_set(persona)
    return [
        finding
        for finding in _as_list(evidence.get("findings"))
        if isinstance(finding, Mapping) and _matches_focus(focus, finding.get("ontology_domain"))
    ]


def _contradictions_in_scope(
    contradictions: Mapping[str, Any],
    persona: ReviewerPersona,
) -> list[dict[str, Any]]:
    del persona
    return [
        finding
        for finding in _as_list(contradictions.get("findings"))
        if isinstance(finding, Mapping)
    ]


# ------------------------------------------------------------------ Scoring


def _penalty_for_dimension(
    *,
    dimension: str,
    weight: float,
    count_high: int,
    count_medium: int,
    count_low: int,
) -> float:
    unit = _PENALTY_UNIT.get(dimension, 8.0)
    signal = count_high * 1.0 + count_medium * 0.5 + count_low * 0.25
    return weight * unit * signal


def _compute_score(
    *,
    persona: ReviewerPersona,
    coverage_gaps: list[dict[str, Any]],
    evidence_findings: list[dict[str, Any]],
    contradictions: list[dict[str, Any]],
    panorama_summary: Mapping[str, Any],
) -> tuple[float, dict[str, Any]]:
    high_uncovered = sum(
        1
        for gap in coverage_gaps
        if (gap.get("priority") or "medium") == "high" and gap.get("coverage_status") == "uncovered"
    )
    medium_uncovered = sum(
        1
        for gap in coverage_gaps
        if (gap.get("priority") or "medium") == "medium"
        and gap.get("coverage_status") == "uncovered"
    )
    partial_coverage = sum(
        1 for gap in coverage_gaps if gap.get("coverage_status") == "partially_covered"
    )

    missing_evidence = sum(1 for f in evidence_findings if f.get("evidence_status") == "missing")
    weak_evidence = sum(1 for f in evidence_findings if f.get("evidence_status") == "weak")

    contradiction_count = len(contradictions)

    failed_gates = int(panorama_summary.get("failed_gates") or 0)
    blocking_reworks = int(panorama_summary.get("blocking_reworks") or 0)

    metrics = {
        "coverage_gaps_high": high_uncovered,
        "coverage_gaps_medium": medium_uncovered,
        "coverage_partial": partial_coverage,
        "evidence_missing": missing_evidence,
        "evidence_weak": weak_evidence,
        "contradictions": contradiction_count,
        "failed_gates": failed_gates,
        "blocking_reworks": blocking_reworks,
    }

    weights = persona.scoring_weights

    penalty = 0.0
    coverage_keys = {
        "mandatory_coverage",
        "regulatory_coverage",
        "overall_readiness",
        "technical_strength",
        "financial_sustainability",
    }
    evidence_keys = {
        "evidence_depth",
        "certifications_presence",
        "claim_credibility",
        "guarantees_coverage",
        "package_reliability",
    }
    contradiction_keys = {
        "formal_consistency",
        "contradiction_absence",
    }
    blocking_keys = {
        "blocking_risk_absence",
        "delivery_feasibility",
        "service_levels",
    }

    for dimension, weight in weights.items():
        if weight <= 0:
            continue
        if dimension in coverage_keys:
            penalty += _penalty_for_dimension(
                dimension=dimension,
                weight=weight,
                count_high=high_uncovered,
                count_medium=medium_uncovered,
                count_low=partial_coverage,
            )
        elif dimension in evidence_keys:
            penalty += _penalty_for_dimension(
                dimension=dimension,
                weight=weight,
                count_high=missing_evidence,
                count_medium=weak_evidence,
                count_low=0,
            )
        elif dimension in contradiction_keys:
            penalty += _penalty_for_dimension(
                dimension=dimension,
                weight=weight,
                count_high=contradiction_count,
                count_medium=0,
                count_low=0,
            )
        elif dimension in blocking_keys:
            penalty += _penalty_for_dimension(
                dimension=dimension,
                weight=weight,
                count_high=failed_gates + blocking_reworks,
                count_medium=0,
                count_low=0,
            )
        # Dimensions without a mapped penalty bucket (e.g. "innovation")
        # intentionally contribute zero — they would need positive
        # signals which we don't compute deterministically yet.

    strictness_multiplier = 1.0 + 0.08 * (persona.strictness - 3)
    penalty *= strictness_multiplier

    score = max(0.0, min(100.0, _BASE_SCORE - penalty))
    metrics["strictness_multiplier"] = round(strictness_multiplier, 3)
    metrics["raw_penalty"] = round(penalty, 2)
    return round(score, 2), metrics


# ------------------------------------------------------------------ Findings


def _coverage_findings(
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for gap in gaps:
        status = gap.get("coverage_status")
        severity = (
            "high"
            if (gap.get("priority") or "medium") == "high" and status == "uncovered"
            else "medium"
        )
        findings.append(
            {
                "category": "coverage_gap",
                "severity": severity,
                "summary": str(gap.get("summary") or "")[:1000],
                "scope_type": "requirement",
                "scope_id": str(gap.get("requirement_id") or ""),
                "supporting_refs": [
                    f"coverage_status:{status or 'unknown'}",
                    f"domain:{gap.get('ontology_domain') or 'altro'}",
                ],
            }
        )
    return findings


def _evidence_findings(
    findings_raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for finding in findings_raw:
        status = finding.get("evidence_status")
        if status == "strong":
            continue
        severity = (
            "high"
            if (finding.get("priority") or "medium") == "high" and status == "missing"
            else "medium"
        )
        collected.append(
            {
                "category": "weak_evidence",
                "severity": severity,
                "summary": str(finding.get("summary") or "")[:1000],
                "scope_type": "evidence",
                "scope_id": str(finding.get("requirement_id") or ""),
                "supporting_refs": [
                    f"evidence_status:{status or 'unknown'}",
                    f"expected:{finding.get('expected_evidence_type') or 'documento'}",
                ],
            }
        )
    return collected


def _contradiction_findings(
    contradictions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for contradiction in contradictions:
        severity = _coerce_severity(contradiction.get("severity"), default="high")
        kind = contradiction.get("kind") or "contradiction"
        scope_id = str(contradiction.get("requirement_id") or contradiction.get("section_id") or "")
        collected.append(
            {
                "category": "contradiction",
                "severity": severity,
                "summary": str(contradiction.get("summary") or "")[:1000],
                "scope_type": "requirement"
                if contradiction.get("requirement_id")
                else "proposal_section",
                "scope_id": scope_id,
                "supporting_refs": [f"kind:{kind}"],
            }
        )
    return collected


def _gate_findings(
    panorama_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    failed_gates = int(panorama_summary.get("failed_gates") or 0)
    blocking_reworks = int(panorama_summary.get("blocking_reworks") or 0)
    if failed_gates > 0:
        collected.append(
            {
                "category": "compliance_risk",
                "severity": "high",
                "summary": f"Ci sono {failed_gates} gate di conformita falliti.",
                "scope_type": "gate",
                "scope_id": "failed_gates",
                "supporting_refs": [f"failed_gates:{failed_gates}"],
            }
        )
    if blocking_reworks > 0:
        collected.append(
            {
                "category": "delivery_risk",
                "severity": "high",
                "summary": f"Ci sono {blocking_reworks} rework bloccanti aperti.",
                "scope_type": "gate",
                "scope_id": "blocking_reworks",
                "supporting_refs": [f"blocking_reworks:{blocking_reworks}"],
            }
        )
    return collected


def _build_questions(
    findings: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    ranked = sorted(
        findings,
        key=lambda item: _SEVERITY_ORDER.get(item.get("severity"), 9),
    )
    questions: list[dict[str, Any]] = []
    for finding in ranked[:limit]:
        category = finding.get("category") or "issue"
        scope_id = finding.get("scope_id") or "n/d"
        questions.append(
            {
                "question": f"Come indirizzate {category} sullo scope {scope_id}?",
                "rationale": finding.get("summary"),
            }
        )
    return questions


# ------------------------------------------------------------------ Entrypoint


def evaluate_persona(
    *,
    persona: ReviewerPersona,
    tool_outputs: Mapping[str, Any],
) -> PersonaEvaluation:
    """Produce a :class:`PersonaEvaluation` for ``persona``.

    ``tool_outputs`` is the dict returned by
    :func:`TenderRehearsalService._run_intelligence_tools` — keyed by
    tool name.
    """

    coverage = _as_mapping(tool_outputs.get("coverage_analyzer"))
    evidence = _as_mapping(tool_outputs.get("evidence_auditor"))
    contradictions = _as_mapping(tool_outputs.get("contradiction_finder"))
    panorama = _as_mapping(tool_outputs.get("compliance_panorama"))
    panorama_summary = _as_mapping(panorama.get("summary"))

    coverage_gaps = _filter_coverage_gaps(coverage, persona)
    evidence_findings = _filter_evidence_findings(evidence, persona)
    contradiction_findings = _contradictions_in_scope(contradictions, persona)

    findings: list[dict[str, Any]] = []
    findings.extend(_coverage_findings(coverage_gaps))
    findings.extend(_evidence_findings(evidence_findings))
    findings.extend(_contradiction_findings(contradiction_findings))
    findings.extend(_gate_findings(panorama_summary))

    findings.sort(key=lambda item: _SEVERITY_ORDER.get(item.get("severity"), 9))

    score, metrics = _compute_score(
        persona=persona,
        coverage_gaps=coverage_gaps,
        evidence_findings=evidence_findings,
        contradictions=contradiction_findings,
        panorama_summary=panorama_summary,
    )

    questions = _build_questions(findings)

    return PersonaEvaluation(
        persona_id=persona.persona_id,
        display_name=persona.display_name,
        reviewer_type=persona.reviewer_type,
        score=score,
        findings=findings,
        questions=questions,
        metrics=metrics,
    )


def counts_by_severity(findings: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        severity = _coerce_severity(finding.get("severity"))
        counts[severity] = counts.get(severity, 0) + 1
    return counts


__all__ = [
    "PersonaEvaluation",
    "counts_by_severity",
    "evaluate_persona",
]
