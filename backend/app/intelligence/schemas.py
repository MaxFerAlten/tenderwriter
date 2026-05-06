"""Pydantic contracts for the TenderWriter intelligence layer."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ONTOLOGY_VERSION = "tw-ontology-v1"


class OntologyDomain(str, Enum):
    AMMINISTRATIVO = "amministrativo"
    ECONOMICO_FINANZIARIO = "economico_finanziario"
    TECNICO = "tecnico"
    PREMIALE = "premiale"
    COMPLIANCE = "compliance"
    CONTRATTUALE = "contrattuale"
    SICUREZZA = "sicurezza"
    ORGANIZZATIVO = "organizzativo"
    DOCUMENTALE = "documentale"
    ALTRO = "altro"


Criticality = Literal["high", "medium", "low"]
EvidenceType = Literal[
    "documentary_proof",
    "narrative_claim",
    "certification",
    "financial_statement",
    "organizational_plan",
    "technical_attachment",
    "mixed",
]
OwnerRole = Literal[
    "legal",
    "finance",
    "technical",
    "bid_manager",
    "security",
    "operations",
    "unknown",
]
EvaluationAxis = Literal["mandatory", "scored", "supporting", "informational"]


class RequirementOntologyTag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ontology_domain: OntologyDomain
    ontology_subdomain: str = Field(min_length=2, max_length=80)
    criticality: Criticality = "medium"
    evidence_type: EvidenceType = "documentary_proof"
    owner_role: OwnerRole = "unknown"
    evaluation_axis: EvaluationAxis = "mandatory"
    ontology_version: str = ONTOLOGY_VERSION
    mapping_confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    matched_rules: list[str] = Field(default_factory=list)


REHEARSAL_CONTRACT_VERSION = "tw-rehearsal-v1"


RehearsalMode = Literal["full", "section", "pre_gate"]
RehearsalHealthProjection = Literal["green", "amber", "red"]
FindingCategory = Literal[
    "coverage_gap",
    "weak_evidence",
    "contradiction",
    "clarity_issue",
    "compliance_risk",
    "delivery_risk",
]
FindingSeverity = Literal["high", "medium", "low"]
RehearsalScopeType = Literal["proposal_section", "requirement", "evidence", "gate"]
RehearsalRecommendationState = Literal["proposed", "accepted", "dismissed"]


class RehearsalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tender_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)
    proposal_section_ids: list[int] = Field(default_factory=list)
    persona_ids: list[str] = Field(default_factory=list)
    mode: RehearsalMode = "full"
    include_forecast_context: bool = True


class PersonaFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FindingCategory
    severity: FindingSeverity
    summary: str = Field(min_length=1, max_length=1000)
    scope_type: RehearsalScopeType
    scope_id: str = Field(min_length=1, max_length=80)
    supporting_refs: list[str] = Field(default_factory=list)


class PersonaQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=500)
    rationale: str | None = Field(default=None, max_length=500)


class PersonaEvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persona_id: str
    display_name: str
    reviewer_type: str
    score: float = Field(ge=0.0, le=100.0)
    findings: list[PersonaFinding] = Field(default_factory=list)
    questions: list[PersonaQuestion] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class RehearsalRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    scope_type: RehearsalScopeType
    scope_id: str = Field(min_length=1, max_length=80)
    severity: FindingSeverity = "medium"
    is_blocking: bool = False
    rationale: str = Field(min_length=1)
    suggested_owner_role: str | None = None
    source_persona_id: str
    status: RehearsalRecommendationState = "proposed"
    linked_rework_action_id: int | None = None


class RehearsalSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int | None = None
    tender_id: int | None = None
    proposal_id: int | None = None
    last_rehearsal_at: datetime | None = None
    overall_score: float | None = None
    persona_divergence: float | None = None
    blocking_findings: int = 0
    high_severity_rework_suggestions: int = 0
    health_projection: RehearsalHealthProjection | None = None
    version: str = REHEARSAL_CONTRACT_VERSION


class RehearsalRecommendationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_to_user_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    severity: FindingSeverity | None = None
    is_blocking: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RehearsalRecommendationDismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class RehearsalRecommendationActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation: RehearsalRecommendationResponse
    rework_action_id: int | None = None


class RehearsalRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    tender_id: int
    proposal_id: int
    mode: RehearsalMode
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    overall_score: float | None = None
    health_projection: RehearsalHealthProjection | None = None
    persona_divergence: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    persona_results: list[PersonaEvaluationResponse] = Field(default_factory=list)
    recommendations: list[RehearsalRecommendationResponse] = Field(default_factory=list)
    error_message: str | None = None
    version: str = REHEARSAL_CONTRACT_VERSION
