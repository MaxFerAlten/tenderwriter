"""FastAPI application for tw-kpi-reason-engine."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

import structlog
from fastapi import FastAPI, status

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
    logger.info(
        "service.starting",
        service=settings.app_name,
        version=settings.app_version,
        base_url=settings.public_base_url,
    )
    yield
    logger.info("service.stopping", service=settings.app_name, version=settings.app_version)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)


def _accepted_message(action: str) -> str:
    return f"{action} accepted for asynchronous processing."


def _placeholder_scores() -> list[KpiScore]:
    codes = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "Q", "E"]
    return [KpiScore(kpi_code=code, label=f"{code} placeholder") for code in codes]


@app.get("/health", response_model=ServiceHealthResponse)
async def health() -> ServiceHealthResponse:
    return ServiceHealthResponse(service=settings.app_name, version=settings.app_version)


@app.post(
    "/v1/tenders",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_tender(payload: TenderSyncRequest) -> AcceptedResponse:
    return AcceptedResponse(
        message=_accepted_message("Tender sync"),
        external_tender_id=payload.external_tender_id,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/events",
    response_model=EventAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_event(
    external_tender_id: str,
    payload: DomainEventRequest,
) -> EventAcceptedResponse:
    return EventAcceptedResponse(
        message=_accepted_message("Domain event ingestion"),
        external_tender_id=external_tender_id,
        event_type=payload.event_type,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/documents/context",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_document_context(
    external_tender_id: str,
    payload: DocumentContextRequest,
) -> AcceptedResponse:
    return AcceptedResponse(
        message=_accepted_message(f"Document context ingestion for {payload.document_id}"),
        external_tender_id=external_tender_id,
    )


@app.post(
    "/v1/tenders/{external_tender_id}/analysis-jobs",
    response_model=AnalysisJobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_analysis_job(
    external_tender_id: str,
    payload: AnalysisJobRequest,
) -> AnalysisJobAcceptedResponse:
    return AnalysisJobAcceptedResponse(
        message=_accepted_message("Analysis job"),
        external_tender_id=external_tender_id,
        job_type=payload.job_type,
    )


@app.get("/v1/tenders/{external_tender_id}/snapshot", response_model=TenderSnapshotResponse)
async def get_snapshot(external_tender_id: str) -> TenderSnapshotResponse:
    return TenderSnapshotResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
        kpis=_placeholder_scores(),
        notes=["Sprint 1 freezes the API contract; analytical computation starts in Sprint 2."],
    )


@app.get("/v1/tenders/{external_tender_id}/diagnostics", response_model=DiagnosticsResponse)
async def get_diagnostics(external_tender_id: str) -> DiagnosticsResponse:
    return DiagnosticsResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
    )


@app.get("/v1/tenders/{external_tender_id}/transitions", response_model=TransitionsResponse)
async def get_transitions(external_tender_id: str) -> TransitionsResponse:
    return TransitionsResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
        items=[
            TransitionItem(
                from_state="S0",
                to_state="S0",
                cause="Sprint 1 placeholder response",
                confidence=1.0,
            )
        ],
    )


@app.get("/v1/tenders/{external_tender_id}/forecast", response_model=ForecastResponse)
async def get_forecast(external_tender_id: str) -> ForecastResponse:
    return ForecastResponse(
        external_tender_id=external_tender_id,
        generated_at=datetime.now(timezone.utc),
        scenarios=[
            ForecastScenario(
                name="not_ready",
                description="Forecasting will be introduced after the first telemetry increments.",
            )
        ],
    )


@app.get("/v1/admin/portfolio/overview", response_model=PortfolioOverviewResponse)
async def get_portfolio_overview() -> PortfolioOverviewResponse:
    return PortfolioOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        tenders_by_health={"unknown": 0},
    )


@app.get(
    "/v1/admin/portfolio/bottlenecks",
    response_model=PortfolioBottlenecksResponse,
)
async def get_portfolio_bottlenecks() -> PortfolioBottlenecksResponse:
    return PortfolioBottlenecksResponse(
        generated_at=datetime.now(timezone.utc),
        items=[
            BottleneckItem(
                external_tender_id="placeholder",
                bottleneck_type="not_ready",
                summary="Portfolio bottlenecks will be populated starting from Sprint 2 telemetry.",
            )
        ],
    )
