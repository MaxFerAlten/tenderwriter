from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.db.database import get_db
from app.models import AIGatewayTarget, LLMSettings

router = APIRouter()

CONNECTION_METHOD_TO_PROVIDER = {
    "llama_cpp": "llama",
    "openrouter": "openrouter",
}


def _require_admin(current_user: UserResponse):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


def _normalize_url(url: str) -> str:
    """Ensure consistent comparison to avoid duplicate targets."""
    return url.rstrip("/")


def _normalize_connection_method(
    connection_method: str | None,
    provider: str | None,
    base_url: str | None = None,
) -> str:
    method = (connection_method or "").strip().lower()
    normalized_provider = (provider or "").strip().lower()
    normalized_base_url = (base_url or "").strip().lower()
    if "openrouter.ai" in normalized_base_url:
        return "openrouter"
    if method in CONNECTION_METHOD_TO_PROVIDER:
        return method
    if normalized_provider == "openrouter":
        return "openrouter"
    return "llama_cpp"


def _normalize_provider(
    provider: str | None,
    connection_method: str | None,
    base_url: str | None = None,
) -> str:
    normalized_provider = (provider or "").strip().lower()
    method = _normalize_connection_method(connection_method, normalized_provider, base_url)
    if method in CONNECTION_METHOD_TO_PROVIDER:
        return CONNECTION_METHOD_TO_PROVIDER[method]
    return normalized_provider or "llama"


def _normalize_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_target_base_url(url: str) -> str:
    return _normalize_url(url)


def _canonicalize_target_base_url(url: str, connection_method: str) -> str:
    normalized = _normalize_target_base_url(url)
    if connection_method != "openrouter":
        return normalized

    suffixes = (
        "/chat/completions",
        "/completions",
        "/models",
    )
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")


def _target_base_urls_conflict(
    existing_target: AIGatewayTarget,
    *,
    route_key: str,
    provider: str,
    base_url: str,
    connection_method: str,
) -> bool:
    if existing_target.route_key != route_key or existing_target.provider != provider:
        return False

    existing_method = _normalize_connection_method(
        existing_target.connection_method,
        existing_target.provider,
        existing_target.base_url,
    )
    return _canonicalize_target_base_url(
        existing_target.base_url,
        existing_method,
    ) == _canonicalize_target_base_url(base_url, connection_method)


def _validate_target_configuration(
    *,
    connection_method: str,
    model_name: str | None,
    api_key: str | None,
) -> None:
    if connection_method != "openrouter":
        return

    if not (model_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenRouter targets require a model_name.",
        )
    if not (api_key or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OpenRouter targets require an API key.",
        )


class LLMSettingsPayload(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    stop_tokens: str | None = None


class LLMSettingsOut(LLMSettingsPayload):
    id: int | None = None


class TargetCreate(BaseModel):
    route_key: str = Field(pattern="^(tender|opencode)$")
    target_kind: str = Field(default="docker")
    connection_method: str = Field(default="llama_cpp")
    provider: str = Field(default="llama")
    base_url: str
    model_name: str | None = None
    api_key: str | None = None
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
    connection_method: str | None = None
    base_url: str | None = None
    model_name: str | None = None
    api_key: str | None = None
    target_kind: str | None = None
    provider: str | None = None


class TargetOut(BaseModel):
    id: int
    route_key: str
    target_kind: str
    connection_method: str
    provider: str
    base_url: str
    model_name: str | None
    has_api_key: bool = False
    enabled: bool
    priority: int
    timeout_ms: int
    use_anonymizer: bool
    metadata_json: dict | None

    model_config = {"from_attributes": True}


class ActiveTargetOut(BaseModel):
    id: int
    route_key: str
    target_kind: str
    connection_method: str
    provider: str
    base_url: str
    model_name: str | None
    api_key: str | None = None
    enabled: bool
    priority: int
    timeout_ms: int
    use_anonymizer: bool
    metadata_json: dict | None

    model_config = {"from_attributes": True}


def _serialize_target(target: AIGatewayTarget) -> TargetOut:
    method = _normalize_connection_method(
        target.connection_method,
        target.provider,
        target.base_url,
    )
    return TargetOut(
        id=target.id,
        route_key=target.route_key,
        target_kind=target.target_kind,
        connection_method=method,
        provider=_normalize_provider(target.provider, method, target.base_url),
        base_url=target.base_url,
        model_name=target.model_name,
        has_api_key=bool((target.api_key or "").strip()),
        enabled=target.enabled,
        priority=target.priority,
        timeout_ms=target.timeout_ms,
        use_anonymizer=target.use_anonymizer,
        metadata_json=target.metadata_json,
    )


def _serialize_active_target(target: AIGatewayTarget) -> ActiveTargetOut:
    method = _normalize_connection_method(
        target.connection_method,
        target.provider,
        target.base_url,
    )
    return ActiveTargetOut(
        id=target.id,
        route_key=target.route_key,
        target_kind=target.target_kind,
        connection_method=method,
        provider=_normalize_provider(target.provider, method, target.base_url),
        base_url=target.base_url,
        model_name=target.model_name,
        api_key=_normalize_api_key(target.api_key),
        enabled=target.enabled,
        priority=target.priority,
        timeout_ms=target.timeout_ms,
        use_anonymizer=target.use_anonymizer,
        metadata_json=target.metadata_json,
    )


@router.get("/llm-settings", response_model=LLMSettingsOut)
async def get_llm_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(LLMSettings).limit(1))
    row = result.scalar_one_or_none()
    if row:
        return {
            "id": row.id,
            "max_tokens": row.max_tokens,
            "temperature": row.temperature,
            "stop_tokens": row.stop_tokens,
        }
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
    return {
        "id": row.id,
        "max_tokens": row.max_tokens,
        "temperature": row.temperature,
        "stop_tokens": row.stop_tokens,
    }


@router.get("/targets", response_model=list[TargetOut])
async def list_targets(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AIGatewayTarget).order_by(AIGatewayTarget.priority))
    items = result.scalars().all()
    return [_serialize_target(item) for item in items]


@router.get("/active-targets", response_model=list[ActiveTargetOut])
async def list_active_targets(
    route: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Internal endpoint for the gateway container to fetch live routing config."""
    stmt = select(AIGatewayTarget).where(AIGatewayTarget.enabled).order_by(AIGatewayTarget.priority)
    if route:
        stmt = stmt.where(AIGatewayTarget.route_key == route)
    result = await db.execute(stmt)
    return [_serialize_active_target(item) for item in result.scalars().all()]


@router.post("/targets", response_model=TargetOut, status_code=201)
async def create_target(
    data: TargetCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    normalized_method = _normalize_connection_method(
        data.connection_method,
        data.provider,
        data.base_url,
    )
    normalized_provider = _normalize_provider(data.provider, normalized_method, data.base_url)
    normalized_base = _normalize_target_base_url(data.base_url)
    normalized_api_key = _normalize_api_key(data.api_key)
    _validate_target_configuration(
        connection_method=normalized_method,
        model_name=data.model_name,
        api_key=normalized_api_key,
    )
    dup_query = await db.execute(
        select(AIGatewayTarget).where(
            AIGatewayTarget.route_key == data.route_key,
            AIGatewayTarget.provider == normalized_provider,
        )
    )
    existing_targets = dup_query.scalars().all()
    if any(
        _target_base_urls_conflict(
            item,
            route_key=data.route_key,
            provider=normalized_provider,
            base_url=normalized_base,
            connection_method=normalized_method,
        )
        for item in existing_targets
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A target with the same route, provider and base_url already exists.",
        )
    target = AIGatewayTarget(
        route_key=data.route_key,
        target_kind=data.target_kind,
        connection_method=normalized_method,
        provider=normalized_provider,
        base_url=normalized_base,
        model_name=data.model_name,
        api_key=normalized_api_key,
        enabled=data.enabled,
        priority=data.priority,
        timeout_ms=data.timeout_ms,
        use_anonymizer=data.use_anonymizer,
        metadata_json=data.metadata_json or {},
    )
    db.add(target)
    await db.flush()
    await db.refresh(target)
    return _serialize_target(target)


@router.put("/targets/{target_id}", response_model=TargetOut)
async def update_target(
    target_id: int,
    data: TargetUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AIGatewayTarget).where(AIGatewayTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    payload = data.model_dump(exclude_unset=True)
    next_method = _normalize_connection_method(
        payload.get("connection_method"),
        payload.get("provider", target.provider),
        payload.get("base_url", target.base_url),
    )
    next_provider = _normalize_provider(
        payload.get("provider", target.provider),
        next_method,
        payload.get("base_url", target.base_url),
    )
    if "base_url" in payload and payload["base_url"]:
        payload["base_url"] = _normalize_target_base_url(payload["base_url"])
    if "api_key" in payload:
        payload["api_key"] = _normalize_api_key(payload["api_key"])
    payload["connection_method"] = next_method
    payload["provider"] = next_provider
    _validate_target_configuration(
        connection_method=next_method,
        model_name=payload.get("model_name", target.model_name),
        api_key=payload.get("api_key", target.api_key),
    )

    new_route = payload.get("route_key", target.route_key)
    new_provider = payload.get("provider", target.provider)
    new_base = payload.get("base_url", target.base_url)
    dup_query = await db.execute(
        select(AIGatewayTarget).where(
            AIGatewayTarget.route_key == new_route,
            AIGatewayTarget.provider == new_provider,
            AIGatewayTarget.id != target_id,
        )
    )
    existing_targets = dup_query.scalars().all()
    if any(
        _target_base_urls_conflict(
            item,
            route_key=new_route,
            provider=new_provider,
            base_url=new_base,
            connection_method=next_method,
        )
        for item in existing_targets
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A target with the same route, provider and base_url already exists.",
        )

    for field, value in payload.items():
        setattr(target, field, value)

    await db.flush()
    await db.refresh(target)
    return _serialize_target(target)


@router.delete("/targets/{target_id}", status_code=204)
async def delete_target(
    target_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AIGatewayTarget).where(AIGatewayTarget.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    await db.delete(target)
    await db.commit()
    return None
