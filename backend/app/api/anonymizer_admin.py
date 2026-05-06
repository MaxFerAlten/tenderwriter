from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.config import settings
from app.db.database import get_db
from app.models import AnonymizerAuditLog, AppSettings
from app.privacy_audit import persist_privacy_audit
from app.privacy_policy import load_privacy_policy_document, resolve_effective_privacy_policy

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


class PolicyRulePayload(BaseModel):
    mode: str | None = Field(default=None, pattern="^(internal_only|external_anonymized)$")
    anonymizer_enabled: bool | None = None


class AnonymizerPolicyPayload(BaseModel):
    default: PolicyRulePayload = Field(default_factory=PolicyRulePayload)
    routes: dict[str, PolicyRulePayload] = Field(default_factory=dict)
    tenders: dict[str, PolicyRulePayload] = Field(default_factory=dict)


class AnonymizerAuditEntry(BaseModel):
    id: int
    action: str
    user_email: str
    user_role: str
    tender_id: int | None = None
    route_key: str | None = None
    llm_route: str | None = None
    anonymized: bool | None = None
    target_id: int | None = None
    target_provider: str | None = None
    target_base_url: str | None = None
    session_token: str | None = None
    success: bool
    error_message: str | None = None
    payload_json: dict[str, Any] | None = None
    created_at: Any

    model_config = {"from_attributes": True}


class AnonymizerLastRagDebugTrace(BaseModel):
    timestamp: str
    mode: str
    route_key: str
    tender_id: int | None = None
    llm_route: str
    anonymizer_enabled: bool
    anonymized: bool
    session_token: str | None = None
    target_id: int | None = None
    target_provider: str | None = None
    target_base_url: str | None = None
    anonymized_prompt_variables: dict[str, str] | None = None
    note: str | None = None


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
        if (
            response.status_code == status.HTTP_400_BAD_REQUEST
            and path.startswith("/v1/")
            and (detail or "").strip().lower() == "missing x-target-url header"
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Anonymizer service is running a legacy relay-only build. "
                    "Rebuild the tw-anonymizer container/image."
                ),
            )
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
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    result = await _proxy_anonymizer(
        "POST",
        "/v1/config",
        payload.model_dump(exclude_none=True),
    )
    await persist_privacy_audit(
        db=db,
        action="anonymizer_config_update",
        current_user=current_user,
        payload=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    return result


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


@router.get("/debug/last-rag", response_model=AnonymizerLastRagDebugTrace | None)
async def get_last_rag_debug_trace(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    rag_engine = getattr(request.app.state, "rag_engine", None)
    if not rag_engine or not hasattr(rag_engine, "get_last_privacy_debug_trace"):
        return None
    return rag_engine.get_last_privacy_debug_trace()


@router.post("/test")
async def test_anonymizer(
    payload: AnonymizerTestPayload,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    result = await _proxy_anonymizer(
        "POST",
        "/v1/anonymize",
        payload.model_dump(exclude_none=True),
    )
    await persist_privacy_audit(
        db=db,
        action="anonymizer_test",
        current_user=current_user,
        session_id=result.get("session_id") if isinstance(result, dict) else None,
        payload={"text_len": len(payload.text), "config": payload.config or {}},
    )
    await db.commit()
    return result


@router.post("/deanonymize")
async def deanonymize_anonymizer_text(
    payload: AnonymizerDeanonymizePayload,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
):
    _require_admin(current_user)
    result = await _proxy_anonymizer(
        "POST",
        "/v1/deanonymize",
        payload.model_dump(exclude_none=True),
    )
    await persist_privacy_audit(
        db=db,
        action="anonymizer_deanonymize",
        current_user=current_user,
        session_id=payload.session_id,
        payload={"mapping_size": result.get("mapping_size")},
    )
    await db.commit()
    return result


@router.get("/policy")
async def get_anonymizer_policy(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    return await load_privacy_policy_document(db)


@router.put("/policy")
async def update_anonymizer_policy(
    payload: AnonymizerPolicyPayload,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = AppSettings(data={})
        db.add(row)

    current_data = dict(row.data) if isinstance(row.data, dict) else {}
    current_data["anonymizer_policy"] = payload.model_dump(exclude_none=True)
    row.data = current_data
    await db.flush()
    await persist_privacy_audit(
        db=db,
        action="anonymizer_policy_update",
        current_user=current_user,
        payload=current_data["anonymizer_policy"],
    )
    await db.commit()
    return current_data["anonymizer_policy"]


@router.get("/policy/effective")
async def get_effective_anonymizer_policy(
    route_key: str = "tender",
    tender_id: int | None = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    policy = await resolve_effective_privacy_policy(
        db,
        route_key=route_key,
        tender_id=tender_id,
    )
    return policy.as_dict()


@router.get("/audit", response_model=list[AnonymizerAuditEntry])
async def list_anonymizer_audit(
    limit: int = 50,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    stmt = (
        select(AnonymizerAuditLog)
        .order_by(AnonymizerAuditLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
