"""FastAPI application for tw-kpi-reason-engine."""

from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging
from time import perf_counter
from typing import Any

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse

from app.analytics import AnalysisSnapshot, compute_analysis_snapshot
from app.auth import require_internal_service
from app.config import settings
from app.contract import (
    FORECAST_DECISION_BUNDLE_VERSION,
    FORECAST_OUTPUT_SCHEMA_VERSION,
    FORMULA_BUNDLE_VERSION,
    HEALTH_RULE_VERSION,
    HEURISTIC_FORECAST_VERSION,
    KPI_CONTRACT_VERSION,
    MARKOV_BACKTEST_VERSION,
    MARKOV_MODEL_VERSION,
    MODEL_BUNDLE_VERSION,
    PROMPT_BUNDLE_VERSION,
    READINESS_RULE_VERSION,
    SEMANTIC_BUNDLE_VERSION,
    SHADOW_BUNDLE_VERSION,
    SNAPSHOT_OUTPUT_SCHEMA_VERSION,
    VERSION_MANIFEST_SCHEMA_VERSION,
)
from app.forecasting import build_forecast_snapshot
from app.job_worker import AnalysisJobWorker
from app.metrics import RuntimeMetrics
from app.migrations import run_migrations
from app.schemas import (
    AcceptedResponse,
    AnalysisJobAcceptedResponse,
    AnalysisJobRequest,
    AnalysisJobStatusResponse,
    BottleneckItem,
    DiagnosticsResponse,
    DocumentContextRequest,
    DomainEventRequest,
    EventAcceptedResponse,
    ForecastDecisionAction,
    ForecastResponse,
    ForecastScenario,
    KpiScore,
    PortfolioBottlenecksResponse,
    PortfolioIntelligenceResponse,
    PortfolioOverviewResponse,
    PortfolioPhaseHotspot,
    PortfolioRiskHotspot,
    PortfolioWatchlistItem,
    RequirementTransitionItem,
    ServiceDependencyStatus,
    ServiceHealthResponse,
    ServiceReadinessResponse,
    ServiceVersionManifestResponse,
    SnapshotHistoryItem,
    TenderSnapshotResponse,
    TenderSyncRequest,
    TransitionItem,
    TransitionsResponse,
)
from app.store import SqliteStore
from app.transition_diagnostics import TransitionSnapshot, build_transition_snapshot

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
    worker = AnalysisJobWorker(
        store,
        run_analysis=lambda job: _run_job(store, job),
        poll_interval_seconds=settings.analysis_job_poll_interval_seconds,
    )
    worker.start()
    app.state.store = store
    app.state.metrics = RuntimeMetrics(
        service_name=settings.app_name,
        service_version=settings.app_version,
        release_channel=settings.release_channel,
    )
    app.state.analysis_job_worker = worker
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
        worker.stop()
        store.close()
        logger.info("service.stopping", service=settings.app_name, version=settings.app_version)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)


@app.middleware("http")
async def collect_runtime_metrics(request: Request, call_next):
    started_at = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        metrics = _get_metrics(request)
        if metrics is not None:
            metrics.record_request(
                method=request.method,
                path=request.url.path,
                status_code=500,
                duration_ms=(perf_counter() - started_at) * 1000,
            )
        raise

    metrics = _get_metrics(request)
    if metrics is not None:
        metrics.record_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=(perf_counter() - started_at) * 1000,
        )
    return response


def get_store(request: Request) -> SqliteStore:
    return request.app.state.store


def _get_metrics(request: Request) -> RuntimeMetrics | None:
    return getattr(request.app.state, "metrics", None)


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
        f"Tracked analysis jobs: {job_count}.",
    ]


def _perform_analysis(
    store: SqliteStore,
    external_tender_id: str,
    *,
    metadata_overrides: dict[str, Any] | None = None,
    generated_at_override: str | None = None,
) -> tuple[dict[str, Any] | None, AnalysisSnapshot | None, TransitionSnapshot | None, dict[str, Any] | None]:
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return None, None, None, None

    events = store.list_domain_events(external_tender_id)
    analysis = compute_analysis_snapshot(tender, events)
    if metadata_overrides:
        merged_metadata = dict(analysis.analysis_metadata or {})
        merged_metadata.update(metadata_overrides)
        analysis = replace(analysis, analysis_metadata=merged_metadata)
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
        generated_at_override=generated_at_override,
    )
    tender = store.get_tender(external_tender_id)
    return tender, analysis, transition_snapshot, snapshot_record


def _perform_history_backfill(
    store: SqliteStore,
    external_tender_id: str,
) -> tuple[dict[str, Any] | None, AnalysisSnapshot | None, TransitionSnapshot | None, dict[str, Any] | None]:
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return None, None, None, None

    events = store.list_domain_events(external_tender_id)
    if not events:
        return _perform_analysis(
            store,
            external_tender_id,
            metadata_overrides={
                "source_job_type": "history_backfill",
                "history_points": 0,
            },
        )

    last_result: tuple[dict[str, Any] | None, AnalysisSnapshot | None, TransitionSnapshot | None, dict[str, Any] | None] = (None, None, None, None)
    cumulative_events: list[dict[str, Any]] = []
    for event in events:
        cumulative_events.append(event)
        occurred_at = str(event["occurred_at"])
        occurred_at_dt = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        analysis = compute_analysis_snapshot(tender, cumulative_events, now=occurred_at_dt)
        merged_metadata = dict(analysis.analysis_metadata or {})
        merged_metadata.update(
            {
                "reconstructed": True,
                "replay_until": occurred_at,
                "replay_source_event_type": event["event_type"],
                "source_job_type": "history_backfill",
                "history_points": len(cumulative_events),
            }
        )
        analysis = replace(analysis, analysis_metadata=merged_metadata)
        transition_snapshot = build_transition_snapshot(
            tender,
            cumulative_events,
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
            generated_at_override=occurred_at,
        )
        tender = store.get_tender(external_tender_id)
        last_result = (tender, analysis, transition_snapshot, snapshot_record)

    final_result = _perform_analysis(
        store,
        external_tender_id,
        metadata_overrides={
            "source_job_type": "history_backfill",
            "history_points": len(events),
        },
    )
    if final_result[3] is not None:
        return final_result
    return last_result


def _run_job(
    store: SqliteStore,
    job: dict[str, Any],
) -> tuple[dict[str, Any] | None, AnalysisSnapshot | None, TransitionSnapshot | None, dict[str, Any] | None]:
    external_tender_id = str(job["external_tender_id"])
    if str(job.get("job_type")) == "history_backfill":
        return _perform_history_backfill(store, external_tender_id)
    return _perform_analysis(store, external_tender_id)


def _load_snapshot_state(
    store: SqliteStore,
    external_tender_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, TransitionSnapshot | None]:
    tender = store.get_tender(external_tender_id)
    if tender is None:
        return None, None, None

    snapshot_record = store.get_latest_snapshot_record(external_tender_id)
    if snapshot_record is None:
        tender, _, transition_snapshot, snapshot_record = _perform_analysis(store, external_tender_id)
        return tender, snapshot_record, transition_snapshot

    transition_snapshot = build_transition_snapshot(
        tender,
        store.list_domain_events(external_tender_id),
        analytical_phase=snapshot_record.get("analytical_phase"),
    )
    return tender, snapshot_record, transition_snapshot


def _snapshot_generated_at(snapshot_record: dict[str, Any] | None) -> datetime:
    if snapshot_record and snapshot_record.get("generated_at"):
        return datetime.fromisoformat(str(snapshot_record["generated_at"]).replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def _snapshot_scores(snapshot_record: dict[str, Any] | None) -> list[KpiScore]:
    return [KpiScore(**payload) for payload in (snapshot_record or {}).get("kpis", [])]


def _build_job_status_response(external_tender_id: str, job_record: dict[str, Any] | None) -> AnalysisJobStatusResponse:
    if job_record is None:
        return AnalysisJobStatusResponse(external_tender_id=external_tender_id)
    return AnalysisJobStatusResponse(
        external_tender_id=external_tender_id,
        job_id=job_record.get("job_id"),
        job_type=job_record.get("job_type"),
        job_status=job_record.get("job_status", "not_requested"),
        requested_by=job_record.get("requested_by"),
        priority=job_record.get("priority"),
        reason=job_record.get("reason"),
        created_at=datetime.fromisoformat(str(job_record["created_at"]).replace("Z", "+00:00")) if job_record.get("created_at") else None,
        started_at=datetime.fromisoformat(str(job_record["started_at"]).replace("Z", "+00:00")) if job_record.get("started_at") else None,
        completed_at=datetime.fromisoformat(str(job_record["completed_at"]).replace("Z", "+00:00")) if job_record.get("completed_at") else None,
        updated_at=datetime.fromisoformat(str(job_record["updated_at"]).replace("Z", "+00:00")) if job_record.get("updated_at") else None,
        latest_snapshot_generated_at=datetime.fromisoformat(str(job_record["latest_snapshot_generated_at"]).replace("Z", "+00:00")) if job_record.get("latest_snapshot_generated_at") else None,
        error_message=job_record.get("error_message"),
    )


def _parse_runtime_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _service_runtime_context(request: Request) -> tuple[SqliteStore, dict[str, Any], RuntimeMetrics, AnalysisJobWorker | None]:
    store = get_store(request)
    runtime = store.get_runtime_metrics()
    metrics = _get_metrics(request) or RuntimeMetrics(
        service_name=settings.app_name,
        service_version=settings.app_version,
        release_channel=settings.release_channel,
    )
    worker = getattr(request.app.state, "analysis_job_worker", None)
    return store, runtime, metrics, worker


def _build_service_readiness_response(request: Request) -> ServiceReadinessResponse:
    store, runtime, _, worker = _service_runtime_context(request)
    queue_depth = int((runtime.get("analysis_jobs") or {}).get("by_status", {}).get("queued", 0) or 0)
    failed_jobs = int((runtime.get("analysis_jobs") or {}).get("by_status", {}).get("failed", 0) or 0)
    mirrored_tenders = int((runtime.get("persistence") or {}).get("mirrored_tenders", 0) or 0)
    latest_snapshot_generated_at = (runtime.get("snapshots") or {}).get("latest_generated_at")
    latest_snapshot_dt = _parse_runtime_datetime(latest_snapshot_generated_at)
    worker_running = bool(getattr(worker, "is_running", False))
    schema_version = store.get_schema_version()

    dependencies: list[ServiceDependencyStatus] = []
    warnings: list[str] = []
    ready = True

    store_status = "ready" if schema_version else "degraded"
    dependencies.append(
        ServiceDependencyStatus(
            name="sqlite_store",
            status=store_status,
            detail=(f"Schema {schema_version} loaded." if schema_version else "Schema version unavailable."),
        )
    )
    if store_status != "ready":
        ready = False
        warnings.append("Database schema version could not be resolved.")

    worker_status = "ready" if worker_running else "degraded"
    dependencies.append(
        ServiceDependencyStatus(
            name="analysis_job_worker",
            status=worker_status,
            detail=("Background worker is running." if worker_running else "Background worker is not running."),
        )
    )
    if worker_status != "ready":
        ready = False
        warnings.append("Analysis job worker is not running.")

    if queue_depth > settings.readiness_queue_warning_threshold:
        ready = False
        warnings.append(
            f"Queued analysis jobs ({queue_depth}) exceed threshold {settings.readiness_queue_warning_threshold}."
        )

    if failed_jobs > settings.readiness_failed_jobs_threshold:
        ready = False
        warnings.append(
            f"Failed analysis jobs ({failed_jobs}) exceed threshold {settings.readiness_failed_jobs_threshold}."
        )

    if mirrored_tenders > 0 and latest_snapshot_dt is None:
        ready = False
        warnings.append("Mirrored tenders exist but no analytical snapshot has been generated yet.")
    elif mirrored_tenders > 0 and latest_snapshot_dt is not None:
        age_seconds = (datetime.now(timezone.utc) - latest_snapshot_dt.astimezone(timezone.utc)).total_seconds()
        if age_seconds > settings.readiness_snapshot_staleness_seconds:
            ready = False
            warnings.append(
                f"Latest snapshot is stale ({int(age_seconds)}s > {settings.readiness_snapshot_staleness_seconds}s)."
            )

    dependencies.append(
        ServiceDependencyStatus(
            name="snapshot_pipeline",
            status=("ready" if latest_snapshot_dt is not None or mirrored_tenders == 0 else "degraded"),
            detail=(
                "No mirrored tenders require snapshot generation yet."
                if mirrored_tenders == 0 and latest_snapshot_dt is None
                else (f"Latest snapshot at {latest_snapshot_generated_at}." if latest_snapshot_generated_at else "Snapshot pipeline waiting for first generation.")
            ),
        )
    )

    return ServiceReadinessResponse(
        status=("ready" if ready else "degraded"),
        service=settings.app_name,
        version=settings.app_version,
        release_channel=settings.release_channel,
        ready=ready,
        checked_at=datetime.now(timezone.utc),
        rollout_policy=settings.normalized_rollout_policy,
        worker_running=worker_running,
        queue_depth=queue_depth,
        failed_jobs=failed_jobs,
        latest_snapshot_generated_at=latest_snapshot_dt,
        readiness_rule_version=READINESS_RULE_VERSION,
        warnings=warnings,
        dependencies=dependencies,
    )


def _build_service_health_response(request: Request) -> ServiceHealthResponse:
    store, _, metrics, _ = _service_runtime_context(request)
    readiness = _build_service_readiness_response(request)
    service_metadata = metrics.service_metadata()
    return ServiceHealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        ready=readiness.ready,
        release_channel=settings.release_channel,
        rollout_policy=settings.normalized_rollout_policy,
        schema_version=store.get_schema_version(),
        started_at=_parse_runtime_datetime(service_metadata.get("started_at")),
        uptime_seconds=service_metadata.get("uptime_seconds"),
        snapshot_output_schema_version=SNAPSHOT_OUTPUT_SCHEMA_VERSION,
        forecast_output_schema_version=FORECAST_OUTPUT_SCHEMA_VERSION,
        version_manifest_schema_version=VERSION_MANIFEST_SCHEMA_VERSION,
        network_boundary=settings.service_network_boundary,
    )


def _build_service_version_manifest(request: Request) -> ServiceVersionManifestResponse:
    store, runtime, _, _ = _service_runtime_context(request)
    entries = [
        {
            "component": "contract",
            "version": KPI_CONTRACT_VERSION,
            "kind": "contract",
            "source": "code",
            "details": {
                "formula_bundle_version": FORMULA_BUNDLE_VERSION,
                "model_bundle_version": MODEL_BUNDLE_VERSION,
                "prompt_bundle_version": PROMPT_BUNDLE_VERSION,
                "health_rule_version": HEALTH_RULE_VERSION,
            },
        },
        {
            "component": "snapshot_output",
            "version": SNAPSHOT_OUTPUT_SCHEMA_VERSION,
            "kind": "output_schema",
            "source": "code",
            "details": {
                "observed_in_store": (runtime.get("version_governance") or {}).get("snapshot_output_schema_versions", {}),
            },
        },
        {
            "component": "forecast_output",
            "version": FORECAST_OUTPUT_SCHEMA_VERSION,
            "kind": "output_schema",
            "source": "code",
            "details": {
                "heuristic_bundle_version": HEURISTIC_FORECAST_VERSION,
                "markov_model_version": MARKOV_MODEL_VERSION,
                "markov_backtest_version": MARKOV_BACKTEST_VERSION,
                "forecast_decision_bundle_version": FORECAST_DECISION_BUNDLE_VERSION,
            },
        },
        {
            "component": "semantic_bundle",
            "version": SEMANTIC_BUNDLE_VERSION,
            "kind": "semantic_engine",
            "source": "code",
            "details": {
                "shadow_bundle_version": SHADOW_BUNDLE_VERSION,
            },
        },
    ]
    for item in store.list_model_versions():
        entries.append(
            {
                "component": item["version_type"],
                "version": item["version_code"],
                "kind": "persisted_model_version",
                "source": "sqlite_store",
                "details": {
                    "created_at": item.get("created_at"),
                    **dict(item.get("descriptor") or {}),
                },
            }
        )
    return ServiceVersionManifestResponse(
        service=settings.app_name,
        version=settings.app_version,
        generated_at=datetime.now(timezone.utc),
        release_channel=settings.release_channel,
        rollout_policy=settings.normalized_rollout_policy,
        schema_version=store.get_schema_version(),
        snapshot_output_schema_version=SNAPSHOT_OUTPUT_SCHEMA_VERSION,
        forecast_output_schema_version=FORECAST_OUTPUT_SCHEMA_VERSION,
        version_manifest_schema_version=VERSION_MANIFEST_SCHEMA_VERSION,
        network_boundary=settings.service_network_boundary,
        entries=entries,
    )


@app.get("/health", response_model=ServiceHealthResponse)
async def health(request: Request) -> ServiceHealthResponse:
    return _build_service_health_response(request)


@app.get("/ready", response_model=ServiceReadinessResponse)
async def ready(request: Request) -> JSONResponse:
    payload = _build_service_readiness_response(request)
    return JSONResponse(
        status_code=(status.HTTP_200_OK if payload.ready else status.HTTP_503_SERVICE_UNAVAILABLE),
        content=payload.model_dump(mode="json"),
    )


@app.get("/version-manifest", response_model=ServiceVersionManifestResponse)
async def version_manifest(request: Request) -> ServiceVersionManifestResponse:
    return _build_service_version_manifest(request)


@app.get("/metrics", response_model=dict[str, Any])
async def get_metrics(request: Request) -> dict[str, Any]:
    _, runtime, metrics, _ = _service_runtime_context(request)
    return metrics.snapshot(store_runtime=runtime)


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_metrics_prometheus(request: Request) -> PlainTextResponse:
    _, runtime, metrics, _ = _service_runtime_context(request)
    if not settings.metrics_text_enabled:
        return PlainTextResponse("metrics_text_export_disabled 1\n")
    return PlainTextResponse(metrics.render_prometheus(store_runtime=runtime), media_type="text/plain; version=0.0.4")


@app.post(
    "/v1/tenders",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_internal_service)],
)
async def sync_tender(
    payload: TenderSyncRequest,
    request: Request,
    store: SqliteStore = Depends(get_store),
) -> AcceptedResponse:
    store.upsert_tender(payload.model_dump(mode="json"))
    _perform_analysis(store, payload.external_tender_id)
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
    request: Request,
    store: SqliteStore = Depends(get_store),
) -> EventAcceptedResponse:
    store.insert_domain_event(external_tender_id, payload.model_dump(mode="json"))
    metrics = _get_metrics(request)
    if metrics is not None:
        metrics.record_domain_event(payload.event_type)
    _perform_analysis(store, external_tender_id)
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
    request: Request,
    store: SqliteStore = Depends(get_store),
) -> AnalysisJobAcceptedResponse:
    if store.get_tender(external_tender_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tender not synchronized yet.")
    job_record = store.enqueue_analysis_job(external_tender_id, payload.model_dump(mode="json"))
    metrics = _get_metrics(request)
    if metrics is not None:
        metrics.record_analysis_job_request(payload.job_type)
    request.app.state.analysis_job_worker.notify()
    return AnalysisJobAcceptedResponse(
        message=_accepted_message("Analysis job"),
        external_tender_id=external_tender_id,
        job_type=payload.job_type,
        job_id=int(job_record["job_id"]),
        job_status=str(job_record["job_status"]),
    )


@app.get(
    "/v1/tenders/{external_tender_id}/analysis-jobs/latest",
    response_model=AnalysisJobStatusResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_latest_analysis_job(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> AnalysisJobStatusResponse:
    return _build_job_status_response(external_tender_id, store.get_latest_analysis_job(external_tender_id))


@app.get(
    "/v1/tenders/{external_tender_id}/snapshot",
    response_model=TenderSnapshotResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_snapshot(
    external_tender_id: str,
    store: SqliteStore = Depends(get_store),
) -> TenderSnapshotResponse:
    tender, snapshot_record, _transition_snapshot = _load_snapshot_state(store, external_tender_id)
    if tender is None or snapshot_record is None:
        return TenderSnapshotResponse(
            external_tender_id=external_tender_id,
            generated_at=_snapshot_generated_at(snapshot_record),
            kpis=_placeholder_scores(),
            notes=["Tender not synchronized yet."],
            analysis_metadata={},
        )

    stored_scores = _snapshot_scores(snapshot_record)
    concrete_codes = {score.kpi_code for score in stored_scores}
    notes = [
        f"Tender mirror synchronized at {tender['last_synced_at']}.",
        *list(snapshot_record.get("notes", [])),
        *_base_notes(external_tender_id, store),
    ]
    return TenderSnapshotResponse(
        external_tender_id=external_tender_id,
        analytical_phase=snapshot_record.get("analytical_phase"),
        health=snapshot_record.get("health", "unknown"),
        generated_at=_snapshot_generated_at(snapshot_record),
        kpis=[*stored_scores, *_placeholder_scores(concrete_codes)],
        notes=notes,
        analysis_metadata=snapshot_record.get("analysis_metadata", {}),
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
    tender, snapshot_record, _transition_snapshot = _load_snapshot_state(store, external_tender_id)
    if tender is None or snapshot_record is None:
        return DiagnosticsResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            summary="Tender not synchronized yet.",
            findings=[],
            analysis_metadata={},
        )

    findings = list(snapshot_record.get('findings', []))
    findings.extend(_base_notes(external_tender_id, store))
    return DiagnosticsResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        summary=str(snapshot_record.get("summary") or "Diagnostics unavailable."),
        findings=findings,
        analysis_metadata=snapshot_record.get("analysis_metadata", {}),
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
    tender, snapshot_record, transition_snapshot = _load_snapshot_state(store, external_tender_id)
    if tender is None or snapshot_record is None:
        return TransitionsResponse(
            external_tender_id=external_tender_id,
            generated_at=datetime.now(timezone.utc),
            summary="Tender not synchronized yet.",
            items=[],
            requirement_items=[],
            history_items=[],
        )

    return TransitionsResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        summary=transition_snapshot.summary if transition_snapshot is not None else "Tender not synchronized yet.",
        items=[TransitionItem(**item) for item in store.list_phase_transitions(external_tender_id)],
        requirement_items=[
            RequirementTransitionItem(**asdict(item))
            for item in (transition_snapshot.requirement_items if transition_snapshot is not None else [])
        ],
        history_items=[SnapshotHistoryItem(**item) for item in store.list_snapshot_history(external_tender_id)],
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
    tender, snapshot_record, transition_snapshot = _load_snapshot_state(store, external_tender_id)
    history_items = store.list_snapshot_history(external_tender_id) if tender is not None else []
    events = store.list_domain_events(external_tender_id) if tender is not None else []
    markov_history_points = store.list_markov_history_points() if tender is not None else []
    forecast = build_forecast_snapshot(
        tender=tender,
        snapshot_record=snapshot_record,
        transition_snapshot=transition_snapshot,
        history_items=history_items,
        events=events,
        markov_history_points=markov_history_points,
    )
    merged_analysis_metadata = {
        **dict((snapshot_record or {}).get("analysis_metadata") or {}),
        **dict(forecast.analysis_metadata or {}),
    }
    return ForecastResponse(
        external_tender_id=external_tender_id,
        generated_at=_snapshot_generated_at(snapshot_record),
        summary=forecast.summary,
        overall_confidence=forecast.overall_confidence,
        scenarios=[
            ForecastScenario(
                name=item.name,
                probability=item.probability,
                description=item.description,
                confidence=item.confidence,
                drivers=item.drivers,
                recommended_action=item.recommended_action,
            )
            for item in forecast.scenarios
        ],
        next_best_actions=[
            ForecastDecisionAction(
                code=item.code,
                title=item.title,
                priority=item.priority,
                rationale=item.rationale,
                expected_impact=item.expected_impact,
                confidence=item.confidence,
                drivers=item.drivers,
            )
            for item in forecast.next_best_actions
        ],
        analysis_metadata=merged_analysis_metadata,
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
        analytical_phases=overview.get("analytical_phases") or {},
        critical_tenders=overview.get("critical_tenders") or [],
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


@app.get(
    "/v1/admin/portfolio/intelligence",
    response_model=PortfolioIntelligenceResponse,
    dependencies=[Depends(require_internal_service)],
)
async def get_portfolio_intelligence(
    store: SqliteStore = Depends(get_store),
) -> PortfolioIntelligenceResponse:
    intelligence = store.get_portfolio_intelligence()
    return PortfolioIntelligenceResponse(
        generated_at=datetime.now(timezone.utc),
        phase_hotspots=[PortfolioPhaseHotspot(**item) for item in intelligence.get("phase_hotspots") or []],
        risk_hotspots=[PortfolioRiskHotspot(**item) for item in intelligence.get("risk_hotspots") or []],
        outcome_trends=intelligence.get("outcome_trends") or {},
        watchlist=[PortfolioWatchlistItem(**item) for item in intelligence.get("watchlist") or []],
        notes=list(intelligence.get("notes") or []),
    )
