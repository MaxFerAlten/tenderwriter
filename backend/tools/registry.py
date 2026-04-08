"""Tool registry — register, lookup, and list available tools.

Simple dict-based registry with no global singletons.
Created via factory function, passed by dependency injection.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.schemas.tools import ToolSpec
from backend.tools.base import BaseTool
from backend.utils.errors import ToolNotFoundError

logger = logging.getLogger("tenderclaw.tools")


class ToolRegistry:
    """Registry of all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Overwrites if name already exists."""
        if tool.name in self._tools:
            logger.warning("Overwriting tool: %s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool:
        """Get a tool by name. Raises ToolNotFoundError if missing."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Tool not found: {name}")
        return tool

    def list_tools(self) -> list[ToolSpec]:
        """List all registered tools as specs."""
        return [t.to_spec() for t in self._tools.values()]

    def list_api_schemas(self) -> list[dict[str, Any]]:
        """List all tools in Anthropic API format."""
        return [t.to_api_schema() for t in self._tools.values()]

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    @property
    def count(self) -> int:
        return len(self._tools)


# Module-level instance — imported by main.py and passed via DI
tool_registry = ToolRegistry()
