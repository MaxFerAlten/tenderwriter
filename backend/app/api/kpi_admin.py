"""Admin KPI API proxy endpoints."""

from __future__ import annotations

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


def _unwrap_query_result(result: KpiClientResult, *, action: str) -> dict[str, Any]:
    if result.delivered:
        return result.response_json

    detail = result.error_message or f"KPI reason engine {action} failed."
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    )


@router.get("/portfolio/overview", response_model=dict[str, Any])
async def get_kpi_portfolio_overview(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_portfolio_overview(),
        action="portfolio overview query",
    )


@router.get("/portfolio/bottlenecks", response_model=dict[str, Any])
async def get_kpi_portfolio_bottlenecks(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_portfolio_bottlenecks(),
        action="portfolio bottlenecks query",
    )


@router.get("/tenders/{tender_id}/snapshot", response_model=dict[str, Any])
async def get_kpi_tender_snapshot(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_tender_snapshot(str(tender_id)),
        action="tender snapshot query",
    )


@router.get("/tenders/{tender_id}/diagnostics", response_model=dict[str, Any])
async def get_kpi_tender_diagnostics(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_tender_diagnostics(str(tender_id)),
        action="tender diagnostics query",
    )


@router.get("/tenders/{tender_id}/transitions", response_model=dict[str, Any])
async def get_kpi_tender_transitions(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_tender_transitions(str(tender_id)),
        action="tender transitions query",
    )


@router.get("/tenders/{tender_id}/forecast", response_model=dict[str, Any])
async def get_kpi_tender_forecast(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    client = KpiReasonEngineClient()
    return _unwrap_query_result(
        await client.get_tender_forecast(str(tender_id)),
        action="tender forecast query",
    )
