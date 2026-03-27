from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnonymizeRequest(BaseModel):
    text: str | None = None
    chunks: list[str] | None = None
    session_id: str | None = None
    config: dict[str, Any] | None = None


class DeanonymizeRequest(BaseModel):
    text: str
    session_id: str


class ConfigRequest(BaseModel):
    entities: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=1)
    strategy: str | None = None
    min_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    mask_cig: bool | None = None
