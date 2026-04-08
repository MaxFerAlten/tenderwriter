"""Base tool interface — every tool inherits from BaseTool."""

from __future__ import annotations

import abc
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from backend.schemas.tools import RiskLevel, ToolResult, ToolSpec

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


class ToolContext(BaseModel):
    """Context passed to every tool execution."""

    session_id: str = ""
    working_directory: str = "."
    message_id: str = ""
    tool_use_id: str = ""
    on_progress: SendFn | None = None
    send: SendFn | None = None

    model_config = {"arbitrary_types_allowed": True}


class BaseTool(abc.ABC):
    """Abstract base for all TenderClaw tools."""

    name: str = ""
    description: str = ""
    risk_level: RiskLevel = RiskLevel.MEDIUM
    is_read_only: bool = False
    concurrency_safe: bool = False

    @abc.abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool's input parameters."""

    @abc.abstractmethod
    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the tool and return a result."""

    def to_spec(self) -> ToolSpec:
        """Convert to a public-facing ToolSpec for the API."""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema(),
            risk_level=self.risk_level,
            is_read_only=self.is_read_only,
            concurrency_safe=self.concurrency_safe,
        )

    def to_api_schema(self) -> dict[str, Any]:
        """Convert to the Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema(),
        }
