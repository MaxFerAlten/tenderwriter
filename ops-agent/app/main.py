"""FastAPI app for the TenderWriter privileged ops agent."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.docker_ops import (
    ContainerAccessError,
    ContainerNotFoundError,
    DockerOpsService,
    DockerUnavailableError,
    NginxReloadError,
)

logger = structlog.get_logger()

ops_service = DockerOpsService(
    allowed_prefix=settings.ops_allowed_prefix,
    frontend_container=settings.ops_frontend_container,
)

app = FastAPI(
    title="TenderWriter Ops Agent",
    version="0.1.0",
    description="Internal privileged Docker operations service for TenderWriter",
)


class NginxReloadRequest(BaseModel):
    read_timeout: int
    connect_timeout: int
    send_timeout: int


def _service_token_is_valid(authorization: str | None, x_service_token: str | None) -> bool:
    expected = settings.ops_agent_token.strip()
    bearer = f"Bearer {expected}"
    return authorization == bearer or x_service_token == expected


async def require_service_token(
    authorization: Annotated[str | None, Header()] = None,
    x_service_token: Annotated[str | None, Header()] = None,
) -> None:
    if not _service_token_is_valid(authorization, x_service_token):
        raise HTTPException(status_code=401, detail="Invalid service token")


def _raise_as_http(exc: Exception) -> None:
    if isinstance(exc, ContainerAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ContainerNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, DockerUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, NginxReloadError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected ops-agent failure") from exc


@app.get("/health")
async def health() -> dict[str, object]:
    capabilities = ops_service.capabilities()
    if not capabilities["available"]:
        raise HTTPException(status_code=503, detail=capabilities["reason"])
    return capabilities


@app.get("/capabilities", dependencies=[Depends(require_service_token)])
async def capabilities() -> dict[str, object]:
    return ops_service.capabilities()


@app.get("/containers", dependencies=[Depends(require_service_token)])
async def list_containers() -> list[dict[str, object]]:
    try:
        return ops_service.list_containers()
    except Exception as exc:  # pragma: no cover - mapped in tests
        logger.warning("Failed to list containers", error=str(exc))
        _raise_as_http(exc)


@app.get("/logs/{container_name}", dependencies=[Depends(require_service_token)])
async def get_logs(container_name: str, tail: int = 100) -> dict[str, object]:
    try:
        return ops_service.get_logs(container_name, tail)
    except Exception as exc:  # pragma: no cover - mapped in tests
        logger.warning("Failed to fetch container logs", container_name=container_name, error=str(exc))
        _raise_as_http(exc)


@app.get("/stats/{container_name}", dependencies=[Depends(require_service_token)])
async def get_stats(container_name: str) -> dict[str, object]:
    try:
        return ops_service.get_stats(container_name)
    except Exception as exc:  # pragma: no cover - mapped in tests
        logger.warning("Failed to fetch container stats", container_name=container_name, error=str(exc))
        _raise_as_http(exc)


@app.post("/frontend/nginx-reload", dependencies=[Depends(require_service_token)])
async def reload_frontend_nginx(payload: NginxReloadRequest) -> dict[str, object]:
    try:
        return ops_service.reload_frontend_nginx(
            read_timeout=payload.read_timeout,
            connect_timeout=payload.connect_timeout,
            send_timeout=payload.send_timeout,
        )
    except Exception as exc:  # pragma: no cover - mapped in tests
        logger.warning("Failed to reload frontend nginx", error=str(exc))
        _raise_as_http(exc)
