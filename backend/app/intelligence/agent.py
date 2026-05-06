"""TenderIntelligenceAgent — read-only orchestrator over the Wave-1 tools.

The agent is a thin, deterministic loop:

    classify intent → select tools (cap 3) → run tools → synthesise answer

All business logic lives in the underlying tools (CoverageAnalyzer,
EvidenceAuditor, CompliancePanorama). The agent never writes to the
database, never mutates compliance gates, rework actions or section
statuses. Recommendations are *suggestions only*; conversion to ReworkAction
happens only via an explicit user action (PR-09).

Intent classification is keyword-based (see :mod:`app.intelligence.prompts`)
so behaviour is reproducible and trivially testable. When/if an LLM-driven
front-end is added it must sit *above* the agent (rephrasing the user's
question), not replace the deterministic dispatch.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.prompts import (
    ANSWER_TEMPLATES,
    INTENT_KEYWORDS,
    INTENT_PRIORITY,
    MAX_TOOLS_PER_QUERY,
    PRIMARY_TOOL_BY_INTENT,
    SECONDARY_TOOLS_BY_INTENT,
)
from app.intelligence.result_models import (
    AgentFinding,
    AgentIntent,
    AgentQueryResult,
    AgentRecommendedAction,
)
from app.intelligence.tool_registry import TenderToolRegistry

logger = logging.getLogger(__name__)


def classify_intent(question: str) -> AgentIntent:
    """Return the highest-priority intent matching the question, or ``unknown``.

    Matching is case-insensitive and substring-based on a fixed keyword
    catalogue. If multiple intents match, the priority order in
    :data:`INTENT_PRIORITY` resolves the tie.
    """

    if not question:
        return "unknown"
    haystack = question.casefold()
    matched: set[AgentIntent] = set()
    for intent, keywords in INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                matched.add(intent)
                break
    for candidate in INTENT_PRIORITY:
        if candidate in matched:
            return candidate
    return "unknown"


def select_tools(intent: AgentIntent, registry: TenderToolRegistry) -> list[str]:
    """Pick the ordered list of tools to run for ``intent``.

    The selection respects :data:`MAX_TOOLS_PER_QUERY` and only includes
    tools that are actually registered. The primary tool comes first; the
    secondary list is appended in declaration order.
    """

    ordered: list[str] = []
    primary = PRIMARY_TOOL_BY_INTENT.get(intent, "compliance_panorama")
    if registry.contains(primary):
        ordered.append(primary)
    for candidate in SECONDARY_TOOLS_BY_INTENT.get(intent, ()):
        if len(ordered) >= MAX_TOOLS_PER_QUERY:
            break
        if candidate in ordered:
            continue
        if registry.contains(candidate):
            ordered.append(candidate)
    return ordered[:MAX_TOOLS_PER_QUERY]


class TenderIntelligenceAgent:
    """Stateless orchestrator over the read-only intelligence tools."""

    def __init__(self, registry: TenderToolRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> TenderToolRegistry:
        return self._registry

    async def query(
        self,
        *,
        db: AsyncSession,
        tender_id: int,
        question: str,
        only_high_priority: bool = False,
    ) -> AgentQueryResult:
        intent = classify_intent(question)
        tool_names = select_tools(intent, self._registry)

        raw_outputs: dict[str, Any] = {}
        for name in tool_names:
            try:
                raw_outputs[name] = await self._registry.run(
                    name,
                    db,
                    self._inputs_for(name, tender_id, only_high_priority),
                )
            except Exception:
                logger.exception(
                    "intelligence_agent.tool_failed",
                    extra={"tool": name, "tender_id": tender_id},
                )
                raw_outputs[name] = {"error": "tool_failed"}

        findings = self._collect_findings(raw_outputs)
        recommendations = self._collect_recommendations(raw_outputs)
        answer = self._synthesise_answer(intent, raw_outputs, tender_id)

        return AgentQueryResult(
            tender_id=tender_id,
            intent=intent,
            question=question,
            tools_used=tool_names,
            answer=answer,
            findings=findings,
            recommended_actions=recommendations,
            raw_tool_outputs=raw_outputs,
        )

    @staticmethod
    def _inputs_for(
        tool_name: str,
        tender_id: int,
        only_high_priority: bool,
    ) -> Mapping[str, Any]:
        if tool_name == "evidence_auditor":
            return {"tender_id": tender_id, "only_high_priority": only_high_priority}
        return {"tender_id": tender_id}

    @staticmethod
    def _collect_findings(raw_outputs: Mapping[str, Any]) -> list[AgentFinding]:
        findings: list[AgentFinding] = []

        coverage = raw_outputs.get("coverage_analyzer") or {}
        for gap in _safe_iter(coverage.get("gaps")):
            if not isinstance(gap, Mapping):
                continue
            severity = "high" if (gap.get("priority") == "high") else "medium"
            findings.append(
                AgentFinding(
                    summary=str(gap.get("summary") or "")[:280],
                    severity=severity,
                    source_tool="coverage_analyzer",
                    requirement_id=_safe_int(gap.get("requirement_id")),
                    ontology_domain=gap.get("ontology_domain"),
                    reference={
                        "coverage_status": gap.get("coverage_status"),
                        "mapped_section_id": gap.get("mapped_section_id"),
                    },
                )
            )

        evidence = raw_outputs.get("evidence_auditor") or {}
        for finding in _safe_iter(evidence.get("findings")):
            if not isinstance(finding, Mapping):
                continue
            evidence_status = finding.get("evidence_status")
            if evidence_status == "strong":
                continue
            severity = (
                "high"
                if (finding.get("priority") == "high" and evidence_status == "missing")
                else "medium"
            )
            findings.append(
                AgentFinding(
                    summary=str(finding.get("summary") or "")[:280],
                    severity=severity,
                    source_tool="evidence_auditor",
                    requirement_id=_safe_int(finding.get("requirement_id")),
                    ontology_domain=finding.get("ontology_domain"),
                    reference={
                        "evidence_status": evidence_status,
                        "expected_evidence_type": finding.get("expected_evidence_type"),
                        "mapped_section_id": finding.get("mapped_section_id"),
                    },
                )
            )

        panorama = raw_outputs.get("compliance_panorama") or {}
        for risk in _safe_iter(panorama.get("top_risks")):
            if not isinstance(risk, Mapping):
                continue
            severity_raw = (risk.get("severity") or "medium").casefold()
            severity = (
                severity_raw if severity_raw in {"low", "medium", "high", "critical"} else "medium"
            )
            findings.append(
                AgentFinding(
                    summary=str(risk.get("summary") or "")[:280],
                    severity=severity,  # type: ignore[arg-type]
                    source_tool="compliance_panorama",
                    reference={"code": risk.get("code")},
                )
            )

        contradictions = raw_outputs.get("contradiction_finder") or {}
        for contradiction in _safe_iter(contradictions.get("findings")):
            if not isinstance(contradiction, Mapping):
                continue
            severity_raw = (contradiction.get("severity") or "high").casefold()
            severity = (
                severity_raw if severity_raw in {"low", "medium", "high", "critical"} else "high"
            )
            findings.append(
                AgentFinding(
                    summary=str(contradiction.get("summary") or "")[:280],
                    severity=severity,  # type: ignore[arg-type]
                    source_tool="contradiction_finder",
                    requirement_id=_safe_int(contradiction.get("requirement_id")),
                    reference={
                        "kind": contradiction.get("kind"),
                        "section_id": contradiction.get("section_id"),
                        "related_requirement_id": contradiction.get("related_requirement_id"),
                    },
                )
            )

        findings.sort(key=lambda item: _SEVERITY_ORDER.get(item.severity, 99))
        return findings[:25]

    @staticmethod
    def _collect_recommendations(
        raw_outputs: Mapping[str, Any],
    ) -> list[AgentRecommendedAction]:
        recommendations: list[AgentRecommendedAction] = []

        coverage = raw_outputs.get("coverage_analyzer") or {}
        for gap in _safe_iter(coverage.get("gaps")):
            if not isinstance(gap, Mapping):
                continue
            if gap.get("coverage_status") != "uncovered":
                continue
            if (gap.get("priority") or "medium") != "high":
                continue
            recommendations.append(
                AgentRecommendedAction(
                    kind="review_uncovered_requirement",
                    summary=f"Mappare a una sezione di proposta: {gap.get('summary') or ''}"[:280],
                    requirement_id=_safe_int(gap.get("requirement_id")),
                    reference={"ontology_domain": gap.get("ontology_domain")},
                )
            )

        evidence = raw_outputs.get("evidence_auditor") or {}
        for finding in _safe_iter(evidence.get("findings")):
            if not isinstance(finding, Mapping):
                continue
            if finding.get("evidence_status") != "missing":
                continue
            recommendations.append(
                AgentRecommendedAction(
                    kind="strengthen_evidence",
                    summary=f"Allegare evidenza ({finding.get('expected_evidence_type') or 'documento'}): {finding.get('summary') or ''}"[
                        :280
                    ],
                    requirement_id=_safe_int(finding.get("requirement_id")),
                    reference={
                        "expected_evidence_type": finding.get("expected_evidence_type"),
                    },
                )
            )

        panorama = raw_outputs.get("compliance_panorama") or {}
        summary = panorama.get("summary") or {}
        if isinstance(summary, Mapping):
            if int(summary.get("failed_gates") or 0) > 0:
                recommendations.append(
                    AgentRecommendedAction(
                        kind="address_failed_gate",
                        summary=f"Risolvere {summary.get('failed_gates')} gate falliti.",
                        reference={"code": "failed_gate"},
                    )
                )
            if int(summary.get("blocking_reworks") or 0) > 0:
                recommendations.append(
                    AgentRecommendedAction(
                        kind="resolve_blocking_rework",
                        summary=f"Sbloccare {summary.get('blocking_reworks')} rework aperti.",
                        reference={"code": "blocking_rework"},
                    )
                )

        contradictions = raw_outputs.get("contradiction_finder") or {}
        for contradiction in _safe_iter(contradictions.get("findings")):
            if not isinstance(contradiction, Mapping):
                continue
            kind = contradiction.get("kind") or "contradiction"
            recommendations.append(
                AgentRecommendedAction(
                    kind="review_contradiction",
                    summary=f"Verificare contraddizione ({kind}): {contradiction.get('summary') or ''}"[
                        :280
                    ],
                    requirement_id=_safe_int(contradiction.get("requirement_id")),
                    reference={
                        "kind": kind,
                        "section_id": contradiction.get("section_id"),
                        "related_requirement_id": contradiction.get("related_requirement_id"),
                    },
                )
            )

        if not recommendations and panorama:
            recommendations.append(
                AgentRecommendedAction(
                    kind="inspect_panorama",
                    summary="Nessuna azione critica suggerita: ispezionare il panorama per dettagli.",
                    reference={"health": panorama.get("health")},
                )
            )

        return recommendations[:20]

    @staticmethod
    def _synthesise_answer(
        intent: AgentIntent,
        raw_outputs: Mapping[str, Any],
        tender_id: int,
    ) -> str:
        template = ANSWER_TEMPLATES.get(intent, ANSWER_TEMPLATES["unknown"])
        coverage_summary = (raw_outputs.get("coverage_analyzer") or {}).get("summary") or {}
        evidence_summary = (raw_outputs.get("evidence_auditor") or {}).get("summary") or {}
        panorama = raw_outputs.get("compliance_panorama") or {}
        panorama_summary = panorama.get("summary") or {}
        contradiction_summary = (raw_outputs.get("contradiction_finder") or {}).get("summary") or {}

        context = {
            "tender_id": tender_id,
            "total": int(coverage_summary.get("total_requirements") or 0),
            "fully_covered": int(coverage_summary.get("fully_covered") or 0),
            "partially_covered": int(coverage_summary.get("partially_covered") or 0),
            "uncovered": int(coverage_summary.get("uncovered") or 0),
            "high_priority_uncovered": int(coverage_summary.get("high_priority_uncovered") or 0),
            "requirements_checked": int(evidence_summary.get("requirements_checked") or 0),
            "strong_evidence": int(evidence_summary.get("strong_evidence") or 0),
            "weak_evidence": int(evidence_summary.get("weak_evidence") or 0),
            "missing_evidence": int(evidence_summary.get("missing_evidence") or 0),
            "health": panorama.get("health") or "unknown",
            "analytical_phase": panorama.get("analytical_phase") or "n/d",
            "open_gates": int(panorama_summary.get("open_gates") or 0),
            "failed_gates": int(panorama_summary.get("failed_gates") or 0),
            "blocking_reworks": int(panorama_summary.get("blocking_reworks") or 0),
            "contradiction_total": int(contradiction_summary.get("total") or 0),
            "contradiction_req_vs_proposal": int(
                contradiction_summary.get("requirement_vs_proposal") or 0
            ),
            "contradiction_proposal_vs_evidence": int(
                contradiction_summary.get("proposal_vs_evidence") or 0
            ),
            "contradiction_req_vs_req": int(
                contradiction_summary.get("requirement_vs_requirement") or 0
            ),
        }
        try:
            return template.format(**context)
        except (KeyError, IndexError):
            return template


_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _safe_iter(value: Any) -> Iterable[Any]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return value
    return ()


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "TenderIntelligenceAgent",
    "classify_intent",
    "select_tools",
]
