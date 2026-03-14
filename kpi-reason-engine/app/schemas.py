"""Pydantic schemas for the KPI reason engine API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

HealthStatus = Literal["healthy"]
StubStatus = Literal["accepted", "not_ready"]
HealthClass = Literal["green", "amber", "red", "unknown"]
DataProvenance = Literal["measured", "inferred", "reconstructed", "unknown"]
AnalysisJobKind = Literal[
    "snapshot_refresh",
    "diagnostics_refresh",
    "forecast_refresh",
    "full_recompute",
]


class ServiceHealthResponse(BaseModel):
    """Health probe response."""

    status: HealthStatus = "healthy"
    service: str
    version: str


class RequirementContext(BaseModel):
    """Requirement metadata synced from the core TenderWriter domain."""

    external_requirement_id: str
    reference: str | None = None
    summary: str | None = None


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


class KpiScore(BaseModel):
    """Structured KPI score payload."""

    kpi_code: str
    value: float | None = None
    label: str | None = None
    health: HealthClass = "unknown"
    provenance: DataProvenance = "unknown"
    confidence: float | None = None
    evidence: list[str] = Field(default_factory=list)


class TenderSnapshotResponse(BaseModel):
    """Snapshot response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    analytical_phase: str | None = None
    health: HealthClass = "unknown"
    generated_at: datetime | None = None
    kpis: list[KpiScore] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DiagnosticsResponse(BaseModel):
    """Diagnostics response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    summary: str = "Diagnostics are not implemented in Sprint 1."
    findings: list[str] = Field(default_factory=list)


class TransitionItem(BaseModel):
    """Single analytical transition item."""

    from_state: str
    to_state: str
    occurred_at: datetime | None = None
    cause: str | None = None
    confidence: float | None = None


class TransitionsResponse(BaseModel):
    """Timeline of analytical transitions for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    items: list[TransitionItem] = Field(default_factory=list)


class ForecastScenario(BaseModel):
    """Single forecast scenario entry."""

    name: str
    probability: float | None = None
    description: str | None = None


class ForecastResponse(BaseModel):
    """Forecast response for a tender."""

    status: StubStatus = "not_ready"
    external_tender_id: str
    generated_at: datetime | None = None
    scenarios: list[ForecastScenario] = Field(default_factory=list)


class PortfolioOverviewResponse(BaseModel):
    """Admin overview across the active tender portfolio."""

    status: StubStatus = "not_ready"
    generated_at: datetime | None = None
    portfolio_health: HealthClass = "unknown"
    total_tenders: int = 0
    tenders_by_health: dict[str, int] = Field(default_factory=dict)


class BottleneckItem(BaseModel):
    """Single bottleneck entry surfaced to the admin UI."""

    external_tender_id: str
    bottleneck_type: str
    summary: str
    health: HealthClass = "unknown"


class PortfolioBottlenecksResponse(BaseModel):
    """Admin bottleneck view across the portfolio."""

    status: StubStatus = "not_ready"
    generated_at: datetime | None = None
    items: list[BottleneckItem] = Field(default_factory=list)
