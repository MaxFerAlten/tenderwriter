"""Tool schemas — tool definitions, inputs, and results."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Tool risk classification for the permission system."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToolSpec(BaseModel):
    """Public-facing tool specification (returned by GET /api/tools)."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    is_read_only: bool = False
    concurrency_safe: bool = False


class ToolInput(BaseModel):
    """Generic tool input wrapper."""

    tool_use_id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Tool execution result."""

    tool_use_id: str
    content: str
    is_error: bool = False


class ToolProgress(BaseModel):
    """Incremental progress event from a running tool."""

    tool_use_id: str
    data: str
