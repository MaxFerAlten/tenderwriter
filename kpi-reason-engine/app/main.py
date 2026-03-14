"""FastAPI application for tw-kpi-reason-engine."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

import structlog
from fastapi import Depends, FastAPI, Request, status

from app.auth import require_internal_service
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


def _placeholder_scores() -> list[KpiScore]:
    codes = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "Q", "E"]
    return [KpiScore(kpi_code=code, label=f"{code} placeholder") for code in codes]


def _base_notes(external_tender_id: str, store: SqliteStore) -> list[str]:
    event_count = store.count_domain_events(external_tender_id)
    document_count = store.count_document_contexts(external_tender_id)
    job_count = store.count_analysis_jobs(external_tender_id)
    return [
        f"Stored events: {event_count}.",
        f"Stored document contexts: {document_count}.",
        f"Queued analysis jobs: {job_count}.",
    ]


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
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return TenderSnapshotResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            kpis=_placeholder_scores(),
            notes=["Tender not synchronized yet."],
        )

    notes = [
        f"Tender mirror synchronized at {tender['last_synced_at']}.",
        *_base_notes(external_tender_id, store),
    ]
    return TenderSnapshotResponse(
        external_tender_id=external_tender_id,
        analytical_phase=tender.get("analytical_phase"),
        health=tender.get("health", "unknown"),
        generated_at=datetime.now(timezone.utc),
        kpis=_placeholder_scores(),
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
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return DiagnosticsResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            summary="Tender not synchronized yet.",
            findings=[],
        )

    return DiagnosticsResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
        summary=(
            "Analytical computation is not ready yet, but the tender mirror and base event telemetry "
            "are available."
        ),
        findings=_base_notes(external_tender_id, store),
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
    tender = store.get_tender(external_tender_id)
    if tender is None:
        items: list[TransitionItem] = []
    else:
        items = [
            TransitionItem(
                from_state="S0",
                to_state="S0",
                cause=f"Current workflow status: {tender.get('current_status') or 'unknown'}.",
                confidence=1.0,
            )
        ]
    return TransitionsResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
        items=items,
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
    tender = store.get_tender(external_tender_id)
    if tender is None:
        description = "Forecasting is blocked until the tender is synchronized."
    else:
        description = (
            "Forecasting will be introduced after KPI scoring is enabled; base telemetry is already persisted."
        )
    return ForecastResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
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
