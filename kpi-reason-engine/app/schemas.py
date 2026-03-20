"""Pydantic schemas for the KPI reason engine API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def _normalize_source_type(value: str | None) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "measured":
        return "observed"
    if normalized in {"observed", "inferred", "reconstructed", "unknown"}:
        return normalized
    return "unknown"


HealthStatus = Literal["healthy"]
ReadinessStatus = Literal["ready", "degraded"]
StubStatus = Literal["accepted", "not_ready"]
HealthClass = Literal["green", "amber", "red", "unknown"]
DataSourceType = Literal["observed", "inferred", "reconstructed", "unknown"]
DataProvenance = Literal["observed", "measured", "inferred", "reconstructed", "unknown"]
ScoreSeverity = Literal["none", "low", "medium", "high", "critical", "unknown"]
AnalysisJobKind = Literal[
    "snapshot_refresh",
    "diagnostics_refresh",
    "forecast_refresh",
    "full_recompute",
    "history_backfill",
]
AnalysisJobLifecycleStatus = Literal["queued", "running", "succeeded", "failed", "not_requested"]
SemanticShadowStatus = Literal["shadow"]
SemanticEvaluationStatus = Literal["official", "shadow", "fallback"]



class ServiceHealthResponse(BaseModel):
    """Health probe response."""

    status: HealthStatus = "healthy"
    service: str
    version: str
    ready: bool = True
    release_channel: str | None = None
    rollout_policy: str | None = None
    schema_version: str | None = None
    started_at: datetime | None = None
    uptime_seconds: float | None = None
    snapshot_output_schema_version: str | None = None
    forecast_output_schema_version: str | None = None
    version_manifest_schema_version: str | None = None
    network_boundary: str | None = None


class ServiceDependencyStatus(BaseModel):
    """Single readiness dependency exposed by the runtime endpoints."""

    name: str
    status: ReadinessStatus = "ready"
    detail: str | None = None


class ServiceReadinessResponse(BaseModel):
    """Readiness probe response with dependency-level details."""

    status: ReadinessStatus = "ready"
    service: str
    version: str
    release_channel: str | None = None
    ready: bool = True
    checked_at: datetime | None = None
    rollout_policy: str | None = None
    worker_running: bool = False
    queue_depth: int = 0
    failed_jobs: int = 0
    latest_snapshot_generated_at: datetime | None = None
    readiness_rule_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    dependencies: list[ServiceDependencyStatus] = Field(default_factory=list)


class VersionManifestEntry(BaseModel):
    """Single versioned component exposed by the service manifest."""

    component: str
    version: str
    kind: str | None = None
    source: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ServiceVersionManifestResponse(BaseModel):
    """Version manifest exposed by the KPI service."""

    status: Literal["available"] = "available"
    service: str
    version: str
    generated_at: datetime | None = None
    release_channel: str | None = None
    rollout_policy: str | None = None
    schema_version: str | None = None
    snapshot_output_schema_version: str | None = None
    forecast_output_schema_version: str | None = None
    version_manifest_schema_version: str | None = None
    network_boundary: str | None = None
    entries: list[VersionManifestEntry] = Field(default_factory=list)


class RequirementContext(BaseModel):
    """Requirement metadata synced from the core TenderWriter domain."""

    external_requirement_id: str
    reference: str | None = None
    summary: str | None = None
    priority: str | None = None
    compliance_status: str | None = None
    mapped_section_id: str | None = None


class SectionContext(BaseModel):
    """Proposal section metadata used to enrich the analytical model."""

    external_section_id: str
    title: str
    owner_department: str | None = None
    status: str | None = None


class TenderSyncRequest(BaseModel):
    """Canonical tender payload sent by tw-backend."""

    external_tender_id: str
    title: str
    customer_name: str | None = None
    due_at: datetime | None = None
    current_status: str | None = None
    departments: list[str] = Field(default_factory=list)
    requirement_contexts: list[RequirementContext] = Field(default_factory=list)
    section_contexts: list[SectionContext] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DomainEventRequest(BaseModel):
    """Domain event envelope consumed by the KPI engine."""

    event_type: str
    occurred_at: datetime
    actor_id: str | None = None
    source: str
    schema_version: str = "1.0.0"
    payload: dict[str, Any] = Field(default_factory=dict)


class DocumentContextRequest(BaseModel):
    """Document-level context made available to future reasoning jobs."""

    document_id: str
    document_type: str
    filename: str | None = None
    extracted_text_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisJobRequest(BaseModel):
    """Asynchronous analysis job request."""

    job_type: AnalysisJobKind = "full_recompute"
    requested_by: str | None = None
    priority: str = "normal"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcceptedResponse(BaseModel):
    """Generic response returned by accepted ingestion endpoints."""

    status: StubStatus = "accepted"
    message: str
    external_tender_id: str


class EventAcceptedResponse(AcceptedResponse):
    """Accepted response enriched with the event type."""

    event_type: str


class AnalysisJobAcceptedResponse(AcceptedResponse):
    """Accepted response enriched with the analysis job type."""

    job_type: AnalysisJobKind
    job_id: int
    job_status: AnalysisJobLifecycleStatus = "queued"


class AnalysisJobStatusResponse(BaseModel):
    """Current lifecycle state of an analysis job."""

    external_tender_id: str
    job_id: int | None = None
    job_type: AnalysisJobKind | None = None
    job_status: AnalysisJobLifecycleStatus = "not_requested"
    requested_by: str | None = None
    priority: str | None = None
    reason: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
    latest_snapshot_generated_at: datetime | None = None
    error_message: str | None = None


class AnalysisMetadata(BaseModel):
    """Versioning and runtime metadata attached to analytical snapshots."""

    formula_bundle_version: str | None = None
    model_bundle_version: str | None = None
    prompt_bundle_version: str | None = None
    snapshot_output_schema_version: str | None = None
    forecast_output_schema_version: str | None = None
    contract_version: str | None = None
    health_rule_version: str | None = None
    score_scale_internal: str | None = None
    score_scale_external: str | None = None
    markov_phase_scope: list[str] = Field(default_factory=list)
    markov_reliable_phase_scope: list[str] = Field(default_factory=list)
    semantic_priority: list[str] = Field(default_factory=list)
    canonical_source_types: list[str] = Field(default_factory=list)
    rollout_policy: str | None = None
    qualitative_engine_kind: str | None = None
    qualitative_engine_mode: str | None = None
    semantic_official_enabled: bool = False
    semantic_engine_kind: str | None = None
    semantic_execution_mode: str | None = None
    semantic_bundle_version: str | None = None
    semantic_kpis: list[str] = Field(default_factory=list)
    semantic_fallback_kpis: list[str] = Field(default_factory=list)
    semantic_fallback_policy_version: str | None = None
    shadow_rollout_enabled: bool = False
    markov_rollout_enabled: bool = False
    calibrated_forecast_enabled: bool = False
    shadow_mode_enabled: bool = False
    shadow_engine_kind: str | None = None
    shadow_execution_mode: str | None = None
    shadow_bundle_version: str | None = None
    shadow_kpis: list[str] = Field(default_factory=list)
    forecast_engine_active: str | None = None
    forecast_engine_candidates: list[str] = Field(default_factory=list)
    forecast_signal_type: str | None = None
    forecast_fallback_reason: str | None = None
    heuristic_bundle_version: str | None = None
    markov_model_active: bool = False
    markov_model_version: str | None = None
    markov_state_scope: list[str] = Field(default_factory=list)
    markov_absorbing_states: list[str] = Field(default_factory=list)
    markov_transition_samples: int | None = None
    markov_dataset_tenders: int | None = None
    markov_current_state_support: int | None = None
    markov_source_mix: dict[str, int] = Field(default_factory=dict)
    markov_bundle_kind: str | None = None
    markov_full_journey_enabled: bool = False
    markov_coverage_ratio: float | None = None
    markov_projected_path: list[str] = Field(default_factory=list)
    markov_backtest_version: str | None = None
    markov_backtest_sample_count: int | None = None
    markov_backtest_submission_accuracy: float | None = None
    markov_backtest_calibration_gap: float | None = None
    forecast_driver_kpis: list[str] = Field(default_factory=list)
    forecast_driver_scores: dict[str, float] = Field(default_factory=dict)
    forecast_primary_action_code: str | None = None
    forecast_primary_action_confidence: float | None = None
    forecast_decision_bundle_version: str | None = None
    engine_kind: str | None = None
    scored_kpis: list[str] = Field(default_factory=list)
    event_count: int | None = None
    requirements_tracked: int | None = None
    sections_tracked: int | None = None
    reconstructed: bool = False
    replay_until: datetime | None = None
    replay_source_event_type: str | None = None
    source_job_type: str | None = None
    history_points: int | None = None


class SemanticCoverageGap(BaseModel):
    """Requirement-level semantic gap surfaced by the evaluator."""

    external_requirement_id: str
    reference: str | None = None
    summary: str | None = None
    priority: str | None = None
    status: str | None = None
    mapped_section_id: str | None = None


class SemanticRiskItem(BaseModel):
    """Structured semantic risk surfaced by the evaluator."""

    code: str
    severity: ScoreSeverity = "unknown"
    summary: str
    related_requirement_id: str | None = None
    evidence: str | None = None


class SemanticDimensionItem(BaseModel):
    """Dimension-level rubric item surfaced by semantic scoring."""

    code: str
    severity: ScoreSeverity = "unknown"
    summary: str
    evidence: str | None = None


class SemanticShadowEvaluation(BaseModel):
    """Side-by-side semantic shadow payload attached to proxy KPIs."""

    enabled: bool = True
    status: SemanticShadowStatus = "shadow"
    engine_kind: str | None = None
    execution_mode: str | None = None
    shadow_score: float | None = None
    proxy_score: float | None = None
    delta_vs_proxy: float | None = None
    health: HealthClass = "unknown"
    confidence: float | None = None
    source_type: DataSourceType = "unknown"
    evidences: list[str] = Field(default_factory=list)
    criticalities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    formula_version: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    coverage_gaps: list[SemanticCoverageGap] = Field(default_factory=list)
    risk_items: list[SemanticRiskItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_shadow_fields(self) -> "SemanticShadowEvaluation":
        self.source_type = _normalize_source_type(self.source_type)
        if self.delta_vs_proxy is None and self.shadow_score is not None and self.proxy_score is not None:
            self.delta_vs_proxy = round(self.shadow_score - self.proxy_score, 1)
        return self


class SemanticEvaluation(BaseModel):
    """Official semantic payload attached to qualitative KPIs."""

    enabled: bool = True
    status: SemanticEvaluationStatus = "official"
    engine_kind: str | None = None
    execution_mode: str | None = None
    semantic_score: float | None = None
    proxy_score: float | None = None
    delta_vs_proxy: float | None = None
    health: HealthClass = "unknown"
    confidence: float | None = None
    source_type: DataSourceType = "unknown"
    evidences: list[str] = Field(default_factory=list)
    criticalities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    formula_version: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    fallback_reason: str | None = None
    coverage_gaps: list[SemanticCoverageGap] = Field(default_factory=list)
    risk_items: list[SemanticRiskItem] = Field(default_factory=list)
    dimension_items: list[SemanticDimensionItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_semantic_fields(self) -> "SemanticEvaluation":
        self.source_type = _normalize_source_type(self.source_type)
        if self.delta_vs_proxy is None and self.semantic_score is not None and self.proxy_score is not None:
            self.delta_vs_proxy = round(self.semantic_score - self.proxy_score, 1)
        return self


class KpiScore(BaseModel):
    """Structured KPI score payload."""

    kpi_code: str
    score: float | None = None
    value: float | None = None
    label: str | None = None
    health: HealthClass = "unknown"
    severity: ScoreSeverity = "unknown"
    source_type: DataSourceType = "unknown"
    provenance: DataProvenance = "unknown"
    confidence: float | None = None
    evidences: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    criticalities: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    formula_version: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    semantic: SemanticEvaluation | None = None
    shadow: SemanticShadowEvaluation | None = None

    @model_validator(mode="after")
    def sync_contract_fields(self) -> "KpiScore":
        if self.score is None and self.value is not None:
            self.score = self.value
        elif self.value is None and self.score is not None:
            self.value = self.score

        normalized_source_type = _normalize_source_type(self.source_type or self.provenance)
        self.source_type = normalized_source_type
        self.provenance = normalized_source_type

        evidence_items = list(self.evidences or self.evidence or [])
        self.evidences = evidence_items
        self.evidence = evidence_items

        recommendation_items = list(self.recommendations or [])
        if not recommendation_items and self.recommendation:
            recommendation_items = [self.recommendation]
        self.recommendations = recommendation_items
        self.recommendation = recommendation_items[0] if recommendation_items else self.recommendation

        if not self.criticalities and self.health in {"amber", "red"}:
            criticality = self.label or (evidence_items[0] if evidence_items else None)
            if criticality:
                self.criticalities = [criticality]
        return self


class TenderSnapshotResponse(BaseModel):
    """Snapshot response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    analytical_phase: str | None = None
    health: HealthClass = "unknown"
    generated_at: datetime | None = None
    kpis: list[KpiScore] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    analysis_metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


class DiagnosticsResponse(BaseModel):
    """Diagnostics response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    summary: str = "Diagnostics are not implemented in Sprint 1."
    findings: list[str] = Field(default_factory=list)
    analysis_metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


class TransitionItem(BaseModel):
    """Single analytical transition item."""

    from_state: str
    to_state: str
    occurred_at: datetime | None = None
    cause: str | None = None
    confidence: float | None = None
    source_event_type: str | None = None
    source_type: DataSourceType = "unknown"
    related_entity_id: str | None = None


class RequirementTransitionItem(BaseModel):
    """Requirement-level driver surfaced in the transition drilldown."""

    external_requirement_id: str
    summary: str | None = None
    priority: str | None = None
    compliance_status: str | None = None
    mapped_section_id: str | None = None
    mapped_section_title: str | None = None
    section_status: str | None = None
    driver_phase: str | None = None
    driver: str
    last_event_type: str | None = None


class SnapshotHistoryItem(BaseModel):
    """Persisted analytical snapshot entry used for history/replay views."""

    snapshot_id: int
    generated_at: datetime | None = None
    analytical_phase: str | None = None
    health: HealthClass = "unknown"
    summary: str | None = None
    reconstructed: bool = False
    replay_until: datetime | None = None
    source_type: DataSourceType = "unknown"
    source_job_type: str | None = None
    replay_source_event_type: str | None = None


class TransitionsResponse(BaseModel):
    """Timeline of analytical transitions for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    summary: str = "Transitions are not implemented in Sprint 1."
    items: list[TransitionItem] = Field(default_factory=list)
    requirement_items: list[RequirementTransitionItem] = Field(default_factory=list)
    history_items: list[SnapshotHistoryItem] = Field(default_factory=list)


class ForecastScenario(BaseModel):
    """Single forecast scenario entry."""

    name: str
    probability: float | None = None
    description: str | None = None
    confidence: float | None = None
    drivers: list[str] = Field(default_factory=list)
    recommended_action: str | None = None


class ForecastDecisionAction(BaseModel):
    """Actionable recommendation derived from the forecast and KPI drivers."""

    code: str
    title: str
    priority: Literal["now", "next", "watch"] = "now"
    rationale: str
    expected_impact: str | None = None
    confidence: float | None = None
    drivers: list[str] = Field(default_factory=list)


class ForecastResponse(BaseModel):
    """Forecast response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    summary: str = "Forecasting is not implemented in Sprint 1."
    overall_confidence: float | None = None
    scenarios: list[ForecastScenario] = Field(default_factory=list)
    next_best_actions: list[ForecastDecisionAction] = Field(default_factory=list)
    analysis_metadata: AnalysisMetadata = Field(default_factory=AnalysisMetadata)


class PortfolioOverviewBucket(BaseModel):
    count: int = 0
    tenders: list[str] = Field(default_factory=list)


class PortfolioOverviewResponse(BaseModel):
    status: StubStatus = "not_ready"
    generated_at: datetime | None = None
    portfolio_health: HealthClass = "unknown"
    total_tenders: int = 0
    tenders_by_health: dict[str, int] = Field(default_factory=dict)
    analytical_phases: dict[str, int] = Field(default_factory=dict)
    critical_tenders: list[str] = Field(default_factory=list)


class BottleneckItem(BaseModel):
    external_tender_id: str
    bottleneck_type: str
    summary: str | None = None
    description: str | None = None
    health: HealthClass = "unknown"
    severity: ScoreSeverity = "unknown"


class PortfolioBottlenecksResponse(BaseModel):
    status: StubStatus = "not_ready"
    generated_at: datetime | None = None
    items: list[BottleneckItem] = Field(default_factory=list)


class PortfolioPhaseHotspot(BaseModel):
    phase: str
    count: int = 0
    summary: str


class PortfolioRiskHotspot(BaseModel):
    code: str
    count: int = 0
    severity: ScoreSeverity = "unknown"
    summary: str


class PortfolioWatchlistItem(BaseModel):
    external_tender_id: str
    title: str
    analytical_phase: str | None = None
    health: HealthClass = "unknown"
    summary: str


class PortfolioIntelligenceResponse(BaseModel):
    status: StubStatus = "not_ready"
    generated_at: datetime | None = None
    phase_hotspots: list[PortfolioPhaseHotspot] = Field(default_factory=list)
    risk_hotspots: list[PortfolioRiskHotspot] = Field(default_factory=list)
    outcome_trends: dict[str, int] = Field(default_factory=dict)
    watchlist: list[PortfolioWatchlistItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

