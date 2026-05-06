"""Admin API for tender planning coverage retrieval configuration."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserResponse, get_current_user
from app.db.database import get_db
from app.models import AppSettings
from app.rag.planningcoverage import (
    DEFAULT_PLANNING_COVERAGE_CONFIG,
    PLANNING_COVERAGE_SETTINGS_KEY,
    classify_query_for_coverage,
    normalize_planning_coverage_config,
)

router = APIRouter()
CURRENT_USER_DEP = Depends(get_current_user)
DB_DEP = Depends(get_db)


def _require_admin(current_user: UserResponse) -> None:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")


class PlanningCoverageConfigPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool = False
    mode: Literal["disabled", "adaptive", "always_on"] = "adaptive"
    slots: dict[str, bool] = Field(
        default_factory=lambda: dict(DEFAULT_PLANNING_COVERAGE_CONFIG["slots"])
    )
    retrievers: dict[str, bool] = Field(
        default_factory=lambda: dict(DEFAULT_PLANNING_COVERAGE_CONFIG["retrievers"])
    )
    topk_per_slot: int = Field(2, alias="topkPerSlot", ge=1, le=10)
    max_sources_per_slot: int = Field(2, alias="maxSourcesPerSlot", ge=1, le=10)
    global_max_coverage_chunks: int = Field(8, alias="globalMaxCoverageChunks", ge=1, le=30)
    min_score: float = Field(0.2, alias="minScore", ge=0.0, le=1.0)
    only_tender_queries: bool = Field(True, alias="onlyTenderQueries")
    always_run_planner: bool = Field(True, alias="alwaysRunPlanner")


class PlanningCoverageTestRequest(BaseModel):
    query: str = Field(..., min_length=2)
    config: dict[str, Any] | None = None


class PlanningCoverageTestResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    query_class: str = Field(alias="queryClass")
    activated: bool
    slots_triggered: list[str] = Field(alias="slotsTriggered")
    generated_queries: dict[str, list[str]] = Field(alias="generatedQueries")
    notes: list[str]


async def _get_settings_row(db: AsyncSession) -> AppSettings | None:
    result = await db.execute(select(AppSettings).limit(1))
    return result.scalar_one_or_none()


async def _load_planning_coverage_settings(db: AsyncSession) -> dict[str, Any]:
    row = await _get_settings_row(db)
    data = row.data if row and isinstance(row.data, dict) else {}
    raw_config = data.get(PLANNING_COVERAGE_SETTINGS_KEY) if isinstance(data, dict) else None
    return normalize_planning_coverage_config(raw_config)


@router.get("/config", response_model=PlanningCoverageConfigPayload)
async def get_planning_coverage_config(
    current_user: UserResponse = CURRENT_USER_DEP,
    db: AsyncSession = DB_DEP,
):
    _require_admin(current_user)
    return PlanningCoverageConfigPayload(**await _load_planning_coverage_settings(db))


@router.post("/config", response_model=PlanningCoverageConfigPayload)
async def update_planning_coverage_config(
    payload: PlanningCoverageConfigPayload,
    current_user: UserResponse = CURRENT_USER_DEP,
    db: AsyncSession = DB_DEP,
):
    _require_admin(current_user)
    row = await _get_settings_row(db)
    if not row:
        row = AppSettings(data={})
        db.add(row)

    current_data = dict(row.data or {}) if isinstance(row.data, dict) else {}
    normalized = normalize_planning_coverage_config(payload.model_dump(by_alias=True))
    current_data[PLANNING_COVERAGE_SETTINGS_KEY] = normalized
    row.data = current_data
    await db.commit()
    await db.refresh(row)
    return PlanningCoverageConfigPayload(**normalized)


@router.post("/test", response_model=PlanningCoverageTestResponse)
async def test_planning_coverage(
    payload: PlanningCoverageTestRequest,
    current_user: UserResponse = CURRENT_USER_DEP,
    db: AsyncSession = DB_DEP,
):
    _require_admin(current_user)
    config = payload.config or await _load_planning_coverage_settings(db)
    plan = classify_query_for_coverage(payload.query, config)
    return PlanningCoverageTestResponse(
        query_class=plan.query_class,
        activated=plan.activated,
        slots_triggered=plan.slots_triggered,
        generated_queries=plan.generated_queries,
        notes=plan.notes,
    )
