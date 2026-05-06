"""Pydantic models for the TenderIntelligenceAgent response envelope.

The agent returns a stable, JSON-serializable structure with five fields:
``intent``, ``tools_used``, ``answer``, ``findings`` and
``recommended_actions``. Plus a ``raw_tool_outputs`` payload for diagnostics
that the FE panel may surface in a debug drawer.

Findings and recommended actions are intentionally narrow vocabularies so
the FE can render them without guessing at the schema. The agent never
creates or mutates ReworkActions / ComplianceGates — recommendations are
suggestions only and require a manual confirmation step (PR-09 hook).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentIntent = Literal[
    "coverage",
    "evidence",
    "panorama",
    "diagnostic",
    "contradiction",
    "unknown",
]
FindingSeverity = Literal["low", "medium", "high", "critical"]
RecommendedActionKind = Literal[
    "review_uncovered_requirement",
    "strengthen_evidence",
    "address_failed_gate",
    "resolve_blocking_rework",
    "inspect_panorama",
    "review_contradiction",
    "follow_up_question",
]


class AgentFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    severity: FindingSeverity = "medium"
    source_tool: str
    requirement_id: int | None = None
    ontology_domain: str | None = None
    reference: dict[str, Any] = Field(default_factory=dict)


class AgentRecommendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RecommendedActionKind
    summary: str
    requirement_id: int | None = None
    reference: dict[str, Any] = Field(default_factory=dict)


class AgentQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int = Field(..., gt=0)
    question: str = Field(..., min_length=1, max_length=2000)
    only_high_priority: bool = False


class AgentQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int
    intent: AgentIntent
    question: str
    tools_used: list[str]
    answer: str
    findings: list[AgentFinding] = Field(default_factory=list)
    recommended_actions: list[AgentRecommendedAction] = Field(default_factory=list)
    raw_tool_outputs: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AgentFinding",
    "AgentIntent",
    "AgentQueryRequest",
    "AgentQueryResult",
    "AgentRecommendedAction",
    "FindingSeverity",
    "RecommendedActionKind",
]
