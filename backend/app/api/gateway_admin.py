from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, UserResponse
from app.db.database import get_db
from app.models import AIGatewayTarget, LLMSettings

router = APIRouter()


def _require_admin(current_user: UserResponse):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


def _normalize_url(url: str) -> str:
    """Ensure consistent comparison to avoid duplicate targets."""
    return url.rstrip("/")




class LLMSettingsPayload(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    stop_tokens: str | None = None

class LLMSettingsOut(LLMSettingsPayload):
    id: int | None = None

class TargetCreate(BaseModel):
    route_key: str = Field(pattern="^(tender|opencode)$")
    target_kind: str = Field(default="docker")
    provider: str = Field(default="llama")
    base_url: str
    model_name: str | None = None
    enabled: bool = True
    priority: int = 1
    timeout_ms: int = 30000
    use_anonymizer: bool = False
    metadata_json: dict | None = None


class TargetUpdate(TargetCreate):
    route_key: str | None = Field(None, pattern="^(tender|opencode)$")
    enabled: bool | None = None
    priority: int | None = None
    timeout_ms: int | None = None
    use_anonymizer: bool | None = None
    base_url: str | None = None
    model_name: str | None = None
    target_kind: str | None = None
    provider: str | None = None


class TargetOut(BaseModel):
    id: int
    route_key: str
    target_kind: str
    provider: str
    base_url: str
    model_name: str | None
    enabled: bool
    priority: int
    timeout_ms: int
    use_anonymizer: bool
    metadata_json: dict | None

    model_config = {"from_attributes": True}



@router.get("/llm-settings", response_model=LLMSettingsOut)
async def get_llm_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(LLMSettings).limit(1))
    row = result.scalar_one_or_none()
    if row:
        return {"id": row.id, "max_tokens": row.max_tokens, "temperature": row.temperature, "stop_tokens": row.stop_tokens}
    from app.config import settings
    return {
        "id": None,
        "max_tokens": getattr(settings, "llama_max_tokens", None),
        "temperature": getattr(settings, "llama_temperature", None),
        "stop_tokens": getattr(settings, "llama_stop_tokens", None),
    }


@router.put("/llm-settings", response_model=LLMSettingsOut)
async def update_llm_settings(
    payload: LLMSettingsPayload,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(LLMSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = LLMSettings()
        db.add(row)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return {"id": row.id, "max_tokens": row.max_tokens, "temperature": row.temperature, "stop_tokens": row.stop_tokens}

@router.get("/targets", response_model=list[TargetOut])
async def list_targets(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AIGatewayTarget).order_by(AIGatewayTarget.priority))
    items = result.scalars().all()
    return items


@router.get("/active-targets", response_model=list[TargetOut])
async def list_active_targets(
    route: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for the gateway container to fetch live routing config."""
    stmt = select(AIGatewayTarget).where(AIGatewayTarget.enabled == True).order_by(AIGatewayTarget.priority)
    if route:
        stmt = stmt.where(AIGatewayTarget.route_key == route)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/targets", response_model=TargetOut, status_code=201)
async def create_target(
    data: TargetCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    normalized_base = _normalize_url(data.base_url)
    dup_query = await db.execute(
        select(AIGatewayTarget).where(
            AIGatewayTarget.route_key == data.route_key,
            AIGatewayTarget.base_url == normalized_base,
            AIGatewayTarget.provider == data.provider,
        )
    )
    if dup_query.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A target with the same route, provider and base_url already exists.",
        )
    target = AIGatewayTarget(
        route_key=data.route_key,
        target_kind=data.target_kind,
        provider=data.provider,
        base_url=normalized_base,
        model_name=data.model_name,
        enabled=data.enabled,
        priority=data.priority,
        timeout_ms=data.timeout_ms,
        use_anonymizer=data.use_anonymizer,
        metadata_json=data.metadata_json or {},
    )
    db.add(target)
    await db.flush()
    await db.refresh(target)
    return target


@router.put("/targets/{target_id}", response_model=TargetOut)
async def update_target(
    target_id: int,
    data: TargetUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(
        select(AIGatewayTarget).where(AIGatewayTarget.id == target_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    payload = data.model_dump(exclude_unset=True)
    if "base_url" in payload and payload["base_url"]:
        payload["base_url"] = _normalize_url(payload["base_url"])

    new_route = payload.get("route_key", target.route_key)
    new_provider = payload.get("provider", target.provider)
    new_base = payload.get("base_url", target.base_url)
    dup_query = await db.execute(
        select(AIGatewayTarget).where(
            AIGatewayTarget.route_key == new_route,
            AIGatewayTarget.provider == new_provider,
            AIGatewayTarget.base_url == new_base,
            AIGatewayTarget.id != target_id,
        )
    )
    if dup_query.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A target with the same route, provider and base_url already exists.",
        )

    for field, value in payload.items():
        setattr(target, field, value)

    await db.flush()
    await db.refresh(target)
    return target


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(
    target_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(
        select(AIGatewayTarget).where(AIGatewayTarget.id == target_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    await db.delete(target)
    await db.commit()
    return None

