from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, UserResponse
from app.db.database import get_db
from app.models import AIGatewayTarget

router = APIRouter()


def _require_admin(current_user: UserResponse):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


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

    class Config:
        orm_mode = True


@router.get("/targets", response_model=list[TargetOut])
async def list_targets(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    result = await db.execute(select(AIGatewayTarget).order_by(AIGatewayTarget.priority))
    items = result.scalars().all()
    return items


@router.post("/targets", response_model=TargetOut, status_code=201)
async def create_target(
    data: TargetCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    target = AIGatewayTarget(
        route_key=data.route_key,
        target_kind=data.target_kind,
        provider=data.provider,
        base_url=data.base_url,
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

    for field, value in data.model_dump(exclude_unset=True).items():
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
    return Response(status_code=204)
