"""Admin KPI API proxy endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import UserResponse, get_current_user
from app.services.kpi_reason_engine import KpiClientResult, KpiReasonEngineClient

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
        return result.response_json

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=_error_detail(result, action),
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
    }


def _diagnostics_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": "KPI service temporarily unavailable.",
        "findings": [detail],
    }


def _transitions_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "summary": detail,
        "items": [],
        "requirement_items": [],
    }


def _forecast_fallback(tender_id: int, detail: str) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "external_tender_id": str(tender_id),
        "generated_at": None,
        "scenarios": [
            {
                "name": "service_unavailable",
                "probability": None,
                "description": detail,
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
        return result.response_json
    fallback.setdefault("error_message", _error_detail(result, action))
    return fallback


@router.get("/portfolio/overview", response_model=dict[str, Any])
async def get_kpi_portfolio_overview(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_portfolio_overview()
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
    return _query_or_fallback(
        result,
        action="portfolio bottlenecks query",
        fallback=_bottlenecks_fallback(_error_detail(result, "portfolio bottlenecks query")),
    )


@router.get("/tenders/{tender_id}/snapshot", response_model=dict[str, Any])
async def get_kpi_tender_snapshot(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_tender_snapshot(str(tender_id))
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
    return _query_or_fallback(
        result,
        action="tender forecast query",
        fallback=_forecast_fallback(tender_id, _error_detail(result, "tender forecast query")),
    )


@router.post("/tenders/{tender_id}/recompute", response_model=dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def recompute_kpi_tender(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_action_result(
        await client.request_analysis_job(
            str(tender_id),
            {
                "job_type": "full_recompute",
                "requested_by": str(current_user.id),
                "priority": "high",
                "reason": "Manual admin recompute",
                "metadata": {
                    "source": "admin-ui",
                    "requested_by_name": current_user.name,
                },
            },
        ),
        action="tender recompute request",
    )


@router.get("/tenders/{tender_id}/analysis-jobs/latest", response_model=dict[str, Any])
async def get_kpi_latest_analysis_job(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    result = await client.get_latest_analysis_job(str(tender_id))
    return _query_or_fallback(
        result,
        action="latest analysis job query",
        fallback=_analysis_job_fallback(tender_id, _error_detail(result, "latest analysis job query")),
    )
