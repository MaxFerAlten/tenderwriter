"""FastAPI application for tw-kpi-reason-engine."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import logging

import structlog
from fastapi import Depends, FastAPI, Request, status

from app.analytics import AnalysisSnapshot, compute_analysis_snapshot
from app.transition_diagnostics import build_transition_snapshot
from app.auth import require_internal_service
from app.migrations import run_migrations
from app.config import settings
from app.schemas import (
    AcceptedResponse,
    AnalysisJobAcceptedResponse,
    AnalysisJobRequest,
    BottleneckItem,
    DiagnosticsResponse,
    DocumentContextRequest,
    DomainEventRequest,
    EventAcceptedResponse,
    ForecastResponse,
    ForecastScenario,
    KpiScore,
    PortfolioBottlenecksResponse,
    RequirementTransitionItem,
    PortfolioOverviewResponse,
    ServiceHealthResponse,
    TenderSnapshotResponse,
    TenderSyncRequest,
    TransitionItem,
    TransitionsResponse,
)
from app.store import SqliteStore

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(message)s")
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations(settings.database_path)
    store = SqliteStore(settings.database_path)
    store.open()
    app.state.store = store
    logger.info(
        "service.starting",
        service=settings.app_name,
        version=settings.app_version,
        base_url=settings.public_base_url,
        database_path=settings.database_path,
    )
    try:
        yield
    finally:
        store.close()
        logger.info("service.stopping", service=settings.app_name, version=settings.app_version)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)


def get_store(request: Request) -> SqliteStore:
    return request.app.state.store


def _accepted_message(action: str) -> str:
    return f"{action} accepted for asynchronous processing."


def _placeholder_scores(exclude: set[str] | None = None) -> list[KpiScore]:
    exclude = exclude or set()
    codes = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "Q", "E"]
    return [KpiScore(kpi_code=code, label=f"{code} placeholder") for code in codes if code not in exclude]


def _base_notes(external_tender_id: str, store: SqliteStore) -> list[str]:
    event_count = store.count_domain_events(external_tender_id)
    document_count = store.count_document_contexts(external_tender_id)
    job_count = store.count_analysis_jobs(external_tender_id)
    return [
        f"Stored events: {event_count}.",
        f"Stored document contexts: {document_count}.",
        f"Queued analysis jobs: {job_count}.",
    ]


def _build_analysis(
    store: SqliteStore,
    external_tender_id: str,
) -> tuple[dict[str, object] | None, AnalysisSnapshot | None, object | None, dict[str, object] | None]:
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return None, None, None, None

    events = store.list_domain_events(external_tender_id)
    analysis = compute_analysis_snapshot(tender, events)
    transition_snapshot = build_transition_snapshot(
        tender,
        events,
        analytical_phase=analysis.analytical_phase,
    )
    store.update_tender_analysis(
        external_tender_id,
        health=analysis.health,
        analytical_phase=analysis.analytical_phase,
    )
    snapshot_record = store.record_analysis_snapshot(
        external_tender_id,
        analysis=analysis,
        transition_snapshot=transition_snapshot,
    )
    tender = store.get_tender(external_tender_id)
    return tender, analysis, transition_snapshot, snapshot_record


def _snapshot_generated_at(snapshot_record: dict[str, object] | None) -> datetime:
    if snapshot_record and snapshot_record.get("generated_at"):
        return datetime.fromisoformat(str(snapshot_record["generated_at"]).replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


@app.get("/health", response_model=ServiceHealthResponse)
async def health() -> ServiceHealthResponse:
    return ServiceHealthResponse(service=settings.app_name, version=settings.app_version)


@app.post(
    "/v1/tenders",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_service)],
)
async def sync_tender(
    payload: TenderSyncRequest,
    store: SqliteStore = Depends(get_store),
) -> AcceptedResponse:
    store.upsert_tender(payload.model_dump(mode="json"))
    _build_analysis(store, payload.external_tender_id)
    return AcceptedResponse(
        message=_accepted_message("Tender sync"),
        external_tender_id=payload.external_tender_id,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/events",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_service)],
)
async def ingest_event(
    external_tender_id: str,
    payload: DomainEventRequest,
    store: SqliteStore = Depends(get_store),
) -> EventAcceptedResponse:
    store.insert_domain_event(external_tender_id, payload.model_dump(mode="json"))
    _build_analysis(store, external_tender_id)
    return EventAcceptedResponse(
        message=_accepted_message("Domain event ingestion"),
        external_tender_id=external_tender_id,
        event_type=payload.event_type,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/documents/context",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_service)],
)
async def ingest_document_context(
    external_tender_id: str,
    payload: DocumentContextRequest,
    store: SqliteStore = Depends(get_store),
) -> AcceptedResponse:
    store.store_document_context(external_tender_id, payload.model_dump(mode="json"))
    return AcceptedResponse(
        message=_accepted_message(f"Document context ingestion for {payload.document_id}"),
        external_tender_id=external_tender_id,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/analysis-jobs",
    response_model=AnalysisJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_service)],
)
async def request_analysis_job(
    external_tender_id: str,
    payload: AnalysisJobRequest,
    store: SqliteStore = Depends(get_store),
) -> AnalysisJobAcceptedResponse:
    store.enqueue_analysis_job(external_tender_id, payload.model_dump(mode="json"))
    return AnalysisJobAcceptedResponse(
        message=_accepted_message("Analysis job"),
        external_tender_id=external_tender_id,
        job_type=payload.job_type,
    )


@app.get(
    "/v1/tenders/{external_tender_id}/snapshot",
    response_model=TenderSnapshotResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_snapshot(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> TenderSnapshotResponse:
    tender, analysis, transition_snapshot, snapshot_record = _build_analysis(store, external_tender_id)
    if tender is None or analysis is None:
        return TenderSnapshotResponse(
            external_tender_id=external_tender_id,
            generated_at=_snapshot_generated_at(snapshot_record),
            kpis=_placeholder_scores(),
            notes=["Tender not synchronized yet."],
        )

    notes = [
        f"Tender mirror synchronized at {tender['last_synced_at']}.",
        *analysis.notes,
        *_base_notes(external_tender_id, store),
    ]
    concrete_codes = {score.kpi_code for score in analysis.kpis}
    return TenderSnapshotResponse(
        external_tender_id=external_tender_id,
        analytical_phase=analysis.analytical_phase,
        health=analysis.health,
        generated_at=_snapshot_generated_at(snapshot_record),
        kpis=[*analysis.kpis, *_placeholder_scores(concrete_codes)],
        notes=notes,
    )


@app.get(
    "/v1/tenders/{external_tender_id}/diagnostics",
    response_model=DiagnosticsResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_diagnostics(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> DiagnosticsResponse:
    tender, analysis, transition_snapshot, snapshot_record = _build_analysis(store, external_tender_id)
    if tender is None or analysis is None:
        return DiagnosticsResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            summary="Tender not synchronized yet.",
            findings=[],
        )

    findings = list((snapshot_record or {}).get('findings', [])) or [*analysis.notes]
    findings.extend(_base_notes(external_tender_id, store))
    return DiagnosticsResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        summary=(snapshot_record or {}).get("summary") or analysis.summary,
        findings=findings,
    )


@app.get(
    "/v1/tenders/{external_tender_id}/transitions",
    response_model=TransitionsResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_transitions(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> TransitionsResponse:
    tender, analysis, transition_snapshot, snapshot_record = _build_analysis(store, external_tender_id)
    if tender is None or analysis is None:
        return TransitionsResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            summary="Tender not synchronized yet.",
            items=[],
            requirement_items=[],
        )

    return TransitionsResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        summary=transition_snapshot.summary if transition_snapshot is not None else 'Tender not synchronized yet.',
        items=[TransitionItem(**item) for item in store.list_phase_transitions(external_tender_id)],
        requirement_items=[RequirementTransitionItem(**asdict(item)) for item in (transition_snapshot.requirement_items if transition_snapshot is not None else [])],
    )


@app.get(
    "/v1/tenders/{external_tender_id}/forecast",
    response_model=ForecastResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_forecast(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> ForecastResponse:
    tender, analysis, transition_snapshot, snapshot_record = _build_analysis(store, external_tender_id)
    if tender is None or analysis is None:
        description = "Forecasting is blocked until the tender is synchronized."
    else:
        description = (
            "Forecasting will remain rule-based in a later sprint; current partial snapshot "
            f"reports {analysis.health} health in {analysis.analytical_phase or 'unknown phase'}."
        )
    return ForecastResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        scenarios=[
            ForecastScenario(
                name="not_ready",
                description=description,
            )
        ],
    )


@app.get(
    "/v1/admin/portfolio/overview",
    response_model=PortfolioOverviewResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_portfolio_overview(
    store: SqliteStore = Depends(get_store),
) -> PortfolioOverviewResponse:
    overview = store.get_portfolio_overview()
    return PortfolioOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        portfolio_health=overview["portfolio_health"],
        total_tenders=overview["total_tenders"],
        tenders_by_health=overview["tenders_by_health"],
    )


@app.get(
    "/v1/admin/portfolio/bottlenecks",
    response_model=PortfolioBottlenecksResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_portfolio_bottlenecks(
    store: SqliteStore = Depends(get_store),
) -> PortfolioBottlenecksResponse:
    return PortfolioBottlenecksResponse(
        generated_at=datetime.now(timezone.utc),
        items=[BottleneckItem(**item) for item in store.list_bottlenecks()],
    )
