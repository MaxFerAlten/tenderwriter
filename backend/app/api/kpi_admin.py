"""Admin KPI API proxy endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.db.database import get_db
from app.models import KpiEventDeliveryStatus, Tender
from app.services.kpi_reason_engine import KpiClientResult, KpiReasonEngineClient, publish_tender_sync

logger = structlog.get_logger(__name__)

router = APIRouter()


def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


def _error_detail(result: KpiClientResult, action: str) -> str:
    return result.error_message or f"KPI reason engine {action} failed."


def _unwrap_action_result(result: KpiClientResult, *, action: str) -> dict[str, Any]:
    if result.delivered:
        payload = dict(result.response_json)
        payload.setdefault("degraded", False)
        payload.setdefault("upstream_status_code", result.status_code)
        return payload

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=_error_detail(result, action),
    )


def _audit_admin_event(*, action: str, current_user: UserResponse, tender_id: int | None = None, result: KpiClientResult | None = None) -> None:
    logger.info(
        "admin_kpi.audit",
        action=action,
        admin_user_id=current_user.id,
        admin_user_email=current_user.email,
        admin_user_role=current_user.role,
        tender_id=tender_id,
        delivered=result.delivered if result is not None else None,
        degraded=(False if result is None else not result.delivered),
        upstream_status_code=None if result is None else result.status_code,
        error_message=None if result is None else result.error_message,
    )


def _overview_fallback(detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "generated_at": None,
        "portfolio_health": "unknown",
        "total_tenders": 0,
        "tenders_by_health": {},
        "notes": [detail],
    }


def _bottlenecks_fallback(detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "generated_at": None,
        "items": [],
        "notes": [detail],
    }


def _snapshot_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "analytical_phase": None,
        "health": "unknown",
        "generated_at": None,
        "kpis": [],
        "notes": [detail],
        "analysis_metadata": {},
    }


def _diagnostics_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": "KPI service temporarily unavailable.",
        "findings": [detail],
        "analysis_metadata": {},
    }


def _transitions_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": detail,
        "items": [],
        "requirement_items": [],
        "history_items": [],
    }


def _forecast_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": detail,
        "overall_confidence": 0.0,
        "scenarios": [
            {
                "name": "service_unavailable",
                "probability": None,
                "description": detail,
                "confidence": 0.0,
                "drivers": [detail],
                "recommended_action": "Retry when the KPI service becomes available.",
            }
        ],
    }


def _analysis_job_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "external_tender_id": str(tender_id),
        "job_id": None,
        "job_type": None,
        "job_status": "degraded",
        "requested_by": None,
        "priority": None,
        "reason": None,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "latest_snapshot_generated_at": None,
        "error_message": detail,
    }


def _query_or_fallback(result: KpiClientResult, *, action: str, fallback: dict[str, Any]) -> dict[str, Any]:
    if result.delivered:
        payload = dict(result.response_json)
        payload.setdefault("degraded", False)
        payload.setdefault("upstream_status_code", result.status_code)
        return payload
    fallback.setdefault("error_message", _error_detail(result, action))
    fallback.setdefault("degraded", True)
    fallback.setdefault("degraded_reason", _error_detail(result, action))
    fallback.setdefault("upstream_status_code", result.status_code)
    return fallback


def _sync_result_metadata(result: KpiClientResult) -> dict[str, Any]:
    return {
        "delivered": result.delivered,
        "upstream_status_code": result.status_code,
        "error_message": result.error_message,
    }


async def _sync_tender_before_analysis_job(
    *,
    tender_id: int,
    current_user: UserResponse,
    db: AsyncSession,
    client: KpiReasonEngineClient,
) -> KpiClientResult:
    sync_event = await publish_tender_sync(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        source="tw-backend",
        client=client,
    )
    if sync_event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tender {tender_id} not found.",
        )

    delivery_status = getattr(sync_event.delivery_status, "value", sync_event.delivery_status)
    return KpiClientResult(
        delivered=delivery_status == KpiEventDeliveryStatus.DELIVERED.value,
        status_code=sync_event.response_status_code,
        response_json=dict(sync_event.response_json or {}),
        error_message=sync_event.error_message,
    )


async def _load_portfolio_tender_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(select(Tender.id).order_by(Tender.id.asc()))
    return list(result.scalars().all())


@router.get("/portfolio/overview", response_model=dict[str, Any])
async def get_kpi_portfolio_overview(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_overview()
    _audit_admin_event(action="portfolio_overview_query", current_user=current_user, result=result)
    return _query_or_fallback(
        result,
        action="portfolio overview query",
        fallback=_overview_fallback(_error_detail(result, "portfolio overview query")),
    )


@router.get("/portfolio/bottlenecks", response_model=dict[str, Any])
async def get_kpi_portfolio_bottlenecks(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_bottlenecks()
    _audit_admin_event(action="portfolio_bottlenecks_query", current_user=current_user, result=result)
    return _query_or_fallback(
        result,
        action="portfolio bottlenecks query",
        fallback=_bottlenecks_fallback(_error_detail(result, "portfolio bottlenecks query")),
    )


@router.post("/portfolio/resync", response_model=dict[str, Any])
async def resync_kpi_portfolio(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    tender_ids = await _load_portfolio_tender_ids(db)
    items: list[dict[str, Any]] = []
    synced_tenders = 0
    failed_tenders = 0

    for tender_id in tender_ids:
        try:
            sync_result = await _sync_tender_before_analysis_job(
                tender_id=tender_id,
                current_user=current_user,
                db=db,
                client=client,
            )
        except HTTPException as exc:
            sync_result = KpiClientResult(
                delivered=False,
                status_code=exc.status_code,
                response_json={},
                error_message=str(exc.detail),
            )
        except Exception as exc:
            sync_result = KpiClientResult(
                delivered=False,
                status_code=None,
                response_json={},
                error_message=str(exc),
            )

        _audit_admin_event(action="portfolio_tender_resync", current_user=current_user, tender_id=tender_id, result=sync_result)
        items.append({"tender_id": tender_id, **_sync_result_metadata(sync_result)})
        if sync_result.delivered:
            synced_tenders += 1
        else:
            failed_tenders += 1

    return {
        "status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_tenders": len(tender_ids),
        "synced_tenders": synced_tenders,
        "failed_tenders": failed_tenders,
        "items": items,
        "notes": [
            "Portfolio resync completed successfully." if failed_tenders == 0 else "Portfolio resync completed with partial failures.",
        ],
    }


@router.get("/tenders/{tender_id}/snapshot", response_model=dict[str, Any])
async def get_kpi_tender_snapshot(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_snapshot(str(tender_id))
    _audit_admin_event(action="tender_snapshot_query", current_user=current_user, tender_id=tender_id, result=result)
    return _query_or_fallback(
        result,
        action="tender snapshot query",
        fallback=_snapshot_fallback(tender_id, _error_detail(result, "tender snapshot query")),
    )


@router.get("/tenders/{tender_id}/diagnostics", response_model=dict[str, Any])
async def get_kpi_tender_diagnostics(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_diagnostics(str(tender_id))
    _audit_admin_event(action="tender_diagnostics_query", current_user=current_user, tender_id=tender_id, result=result)
    return _query_or_fallback(
        result,
        action="tender diagnostics query",
        fallback=_diagnostics_fallback(tender_id, _error_detail(result, "tender diagnostics query")),
    )


@router.get("/tenders/{tender_id}/transitions", response_model=dict[str, Any])
async def get_kpi_tender_transitions(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_transitions(str(tender_id))
    _audit_admin_event(action="tender_transitions_query", current_user=current_user, tender_id=tender_id, result=result)
    return _query_or_fallback(
        result,
        action="tender transitions query",
        fallback=_transitions_fallback(tender_id, _error_detail(result, "tender transitions query")),
    )


@router.get("/tenders/{tender_id}/forecast", response_model=dict[str, Any])
async def get_kpi_tender_forecast(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_forecast(str(tender_id))
    _audit_admin_event(action="tender_forecast_query", current_user=current_user, tender_id=tender_id, result=result)
    return _query_or_fallback(
        result,
        action="tender forecast query",
        fallback=_forecast_fallback(tender_id, _error_detail(result, "tender forecast query")),
    )


@router.post("/tenders/{tender_id}/recompute", response_model=dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def recompute_kpi_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    sync_result = await _sync_tender_before_analysis_job(
        tender_id=tender_id,
        current_user=current_user,
        db=db,
        client=client,
    )
    _audit_admin_event(action="tender_resync_before_recompute", current_user=current_user, tender_id=tender_id, result=sync_result)
    if not sync_result.delivered:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(sync_result, "tender resync before recompute"),
        )

    result = await client.request_analysis_job(
        str(tender_id),
        {
            "job_type": "full_recompute",
            "requested_by": str(current_user.id),
            "priority": "high",
            "reason": "Manual admin recompute",
            "metadata": {
                "source": "admin-ui",
                "requested_by_name": current_user.name,
                "resync_before_job": True,
            },
        },
    )
    _audit_admin_event(action="tender_recompute_request", current_user=current_user, tender_id=tender_id, result=result)
    payload = _unwrap_action_result(result, action="tender recompute request")
    payload.setdefault("tender_sync", _sync_result_metadata(sync_result))
    return payload


@router.post("/tenders/{tender_id}/history/backfill", response_model=dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def backfill_kpi_tender_history(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    sync_result = await _sync_tender_before_analysis_job(
        tender_id=tender_id,
        current_user=current_user,
        db=db,
        client=client,
    )
    _audit_admin_event(action="tender_resync_before_history_backfill", current_user=current_user, tender_id=tender_id, result=sync_result)
    if not sync_result.delivered:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(sync_result, "tender resync before history backfill"),
        )

    result = await client.request_analysis_job(
        str(tender_id),
        {
            "job_type": "history_backfill",
            "requested_by": str(current_user.id),
            "priority": "high",
            "reason": "Manual admin history backfill",
            "metadata": {
                "source": "admin-ui",
                "requested_by_name": current_user.name,
                "resync_before_job": True,
            },
        },
    )
    _audit_admin_event(action="tender_history_backfill_request", current_user=current_user, tender_id=tender_id, result=result)
    payload = _unwrap_action_result(result, action="tender history backfill request")
    payload.setdefault("tender_sync", _sync_result_metadata(sync_result))
    return payload


@router.get("/tenders/{tender_id}/analysis-jobs/latest", response_model=dict[str, Any])
async def get_kpi_latest_analysis_job(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_latest_analysis_job(str(tender_id))
    _audit_admin_event(action="latest_analysis_job_query", current_user=current_user, tender_id=tender_id, result=result)
    return _query_or_fallback(
        result,
        action="latest analysis job query",
        fallback=_analysis_job_fallback(tender_id, _error_detail(result, "latest analysis job query")),
    )
