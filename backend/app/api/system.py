"""TenderWriter system APIs backed by the internal privileged ops-agent."""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.config import settings
from app.db.database import get_db
from app.models.app_settings import AppSettings
from app.services.ops_agent import OpsAgentClient, OpsAgentClientResult

logger = structlog.get_logger()
router = APIRouter()


def admin_required(current_user: UserResponse = Depends(get_current_user)):
    """Dependency to check if user is admin."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


class NginxConfigUpdate(BaseModel):
    read_timeout: int
    connect_timeout: int
    send_timeout: int


def _build_capabilities_payload(result: OpsAgentClientResult) -> dict[str, dict[str, Any]]:
    if not result.delivered:
        reason = result.error_message or "Ops agent unavailable."
        return {
            "ops_agent": {"available": False, "reason": reason},
            "ops_monitoring": {"available": False, "reason": reason},
            "nginx_hot_reload": {"available": False, "reason": reason},
        }

    payload = result.response_json
    ops_reason = payload.get("reason")
    monitoring_available = bool(payload.get("ops_monitoring"))
    monitoring_reason = (
        None if monitoring_available else (ops_reason or "Ops monitoring unavailable.")
    )
    nginx_available = bool(payload.get("nginx_hot_reload"))
    nginx_reason = (
        None
        if nginx_available
        else (
            payload.get("nginx_hot_reload_reason") or ops_reason or "Nginx hot reload unavailable."
        )
    )
    return {
        "ops_agent": {"available": bool(payload.get("available")), "reason": ops_reason},
        "ops_monitoring": {"available": monitoring_available, "reason": monitoring_reason},
        "nginx_hot_reload": {"available": nginx_available, "reason": nginx_reason},
    }


def _raise_for_ops_result(result: OpsAgentClientResult, *, fallback_detail: str) -> None:
    detail = result.response_json.get("detail") or result.error_message or fallback_detail
    status_code = result.status_code or 503
    raise HTTPException(status_code=status_code, detail=detail)


@router.get("/capabilities", dependencies=[Depends(admin_required)])
async def get_system_capabilities() -> dict[str, dict[str, Any]]:
    """Report whether privileged ops features are available in this environment."""
    result = await OpsAgentClient().get_capabilities()
    return _build_capabilities_payload(result)


@router.get("/containers", dependencies=[Depends(admin_required)])
async def list_containers() -> list[dict[str, Any]]:
    """List allowlisted TenderWriter containers via the internal ops-agent."""
    result = await OpsAgentClient().list_containers()
    if not result.delivered:
        _raise_for_ops_result(result, fallback_detail="Unable to list containers.")
    return result.response_json.get("data", result.response_json)


@router.get("/logs/{container_name}", dependencies=[Depends(admin_required)])
async def get_container_logs(container_name: str, tail: int = 100):
    """Retrieve recent logs for an allowlisted container via ops-agent."""
    result = await OpsAgentClient().get_logs(container_name, tail=tail)
    if not result.delivered:
        _raise_for_ops_result(result, fallback_detail="Unable to fetch container logs.")
    return result.response_json


@router.get("/stats/{container_name}", dependencies=[Depends(admin_required)])
async def get_container_stats(container_name: str):
    """Retrieve realtime stats for an allowlisted container via ops-agent."""
    result = await OpsAgentClient().get_stats(container_name)
    if not result.delivered:
        _raise_for_ops_result(result, fallback_detail="Unable to fetch container stats.")
    return result.response_json


@router.post("/nginx-timeout", dependencies=[Depends(admin_required)])
async def update_nginx_timeout(config: NginxConfigUpdate):
    """Apply persisted Nginx timeout settings live via the internal ops-agent."""
    result = await OpsAgentClient().reload_frontend_nginx(config.model_dump())
    if not result.delivered:
        _raise_for_ops_result(
            result, fallback_detail="Unable to apply frontend Nginx timeout changes."
        )
    logger.info("Nginx timeout updated via ops-agent", timeouts=config.model_dump())
    return result.response_json


# ── App Settings (generic key-value store) ──


class AppSettingsPayload(BaseModel):
    """Flexible payload — any key-value pair is accepted."""

    rag_model: str | None = None
    nginx_read_timeout: int | None = None
    nginx_connect_timeout: int | None = None
    nginx_send_timeout: int | None = None
    admin_enabled: bool | None = None
    anonymizer_enabled: bool | None = None


@router.get("/app-settings")
async def get_app_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all saved app settings."""
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and row.data:
        return row.data
    # Return defaults
    return {
        "rag_model": "Llama 3 (8b)",
        "nginx_read_timeout": 300,
        "nginx_connect_timeout": 300,
        "nginx_send_timeout": 300,
        "admin_enabled": True,
        "anonymizer_enabled": settings.anonymizer_enabled,
    }


@router.put("/app-settings")
async def update_app_settings(
    payload: AppSettingsPayload,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save app settings to the database."""
    # Only admins can save settings
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = AppSettings(data={})
        db.add(row)

    current_data = dict(row.data) if row.data else {}
    # Merge only non-None values from the payload
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            current_data[key] = value
    row.data = current_data
    await db.flush()
    await db.refresh(row)
    logger.info("App settings updated", data=row.data)
    return row.data


@router.post("/rebuild-bm25", dependencies=[Depends(admin_required)])
async def rebuild_bm25_index(
    request: Request,
):
    """Manually trigger a full rebuild of the BM25 sparse index."""
    rag_engine = getattr(request.app.state, "rag_engine", None)
    if not rag_engine:
        raise HTTPException(status_code=503, detail="RAG Engine not available")

    await rag_engine.ensure_initialized()
    if not rag_engine.sparse_retriever:
        raise HTTPException(status_code=503, detail="Sparse retriever not initialized")

    try:
        rag_engine._bootstrap_sparse_retriever()
        size = rag_engine.sparse_retriever.corpus_size
        logger.info("Manual BM25 rebuild completed", corpus_size=size)
        return {"status": "ok", "message": "BM25 index rebuilt successfully", "corpus_size": size}
    except Exception as e:
        logger.error("Failed to rebuild BM25 index", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
