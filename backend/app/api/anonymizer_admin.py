from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import UserResponse, get_current_user
from app.config import settings

router = APIRouter()


def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


class AnonymizerConfigPayload(BaseModel):
    entities: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)
    strategy: str | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mask_cig: bool | None = None


class AnonymizerTestPayload(BaseModel):
    text: str
    session_id: str | None = None
    config: dict[str, Any] | None = None


class AnonymizerDeanonymizePayload(BaseModel):
    text: str
    session_id: str


async def _proxy_anonymizer(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = settings.anonymizer_url.strip()
    if not base_url:
        raise HTTPException(status_code=503, detail="Anonymizer URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=settings.anonymizer_timeout) as client:
            response = await client.request(
                method,
                f"{base_url.rstrip('/')}{path}",
                json=payload,
                headers={
                    **(
                        {"x-anonymizer-admin-token": settings.anonymizer_admin_token}
                        if settings.anonymizer_admin_token
                        else {}
                    ),
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Anonymizer service unavailable") from exc

    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text or "Invalid anonymizer response"}

    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        raise HTTPException(
            status_code=response.status_code,
            detail=detail or "Anonymizer request failed",
        )

    if not isinstance(body, dict):
        raise HTTPException(status_code=502, detail="Invalid anonymizer response payload")
    return body


@router.get("/config")
async def get_anonymizer_config(
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    return await _proxy_anonymizer("GET", "/v1/config")


@router.post("/config")
async def update_anonymizer_config(
    payload: AnonymizerConfigPayload,
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    return await _proxy_anonymizer(
        "POST",
        "/v1/config",
        payload.model_dump(exclude_none=True),
    )


@router.get("/stats")
async def get_anonymizer_stats(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    stats = await _proxy_anonymizer("GET", "/v1/stats")
    rag_engine = getattr(request.app.state, "rag_engine", None)
    if rag_engine and hasattr(rag_engine, "get_anonymizer_runtime_stats"):
        stats.update(rag_engine.get_anonymizer_runtime_stats())
    return stats


@router.post("/test")
async def test_anonymizer(
    payload: AnonymizerTestPayload,
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    return await _proxy_anonymizer(
        "POST",
        "/v1/anonymize",
        payload.model_dump(exclude_none=True),
    )


@router.post("/deanonymize")
async def deanonymize_anonymizer_text(
    payload: AnonymizerDeanonymizePayload,
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    return await _proxy_anonymizer(
        "POST",
        "/v1/deanonymize",
        payload.model_dump(exclude_none=True),
    )
