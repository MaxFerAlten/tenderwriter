"""MCP Tool Bridge — expose MCP server tools as TenderClaw tools.

Creates dynamic BaseTool instances for each tool discovered from MCP servers,
so they can be registered in tool_registry and used by agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.mcp.client import mcp_manager
from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.mcp.bridge")


class McpToolProxy(BaseTool):
    """Proxy that forwards execution to an MCP server tool."""

    risk_level = RiskLevel.MEDIUM
    is_read_only = False
    concurrency_safe = False

    def __init__(self, tool_def: dict[str, Any]) -> None:
        self.name = tool_def["name"]
        self.description = tool_def.get("description", f"MCP tool: {self.name}")
        self._schema = tool_def.get("inputSchema", {"type": "object", "properties": {}})
        self._server = tool_def.get("_server", "")
        self._original_name = tool_def.get("_original_name", self.name)

    def input_schema(self) -> dict[str, Any]:
        return self._schema

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            result = await mcp_manager.call_tool(self.name, tool_input)
            content_parts = result.get("content", [])

            if isinstance(content_parts, list):
                text = "\n".join(
                    p.get("text", json.dumps(p)) if isinstance(p, dict) else str(p)
                    for p in content_parts
                )
            elif isinstance(content_parts, str):
                text = content_parts
            else:
                text = json.dumps(content_parts)

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=text or "(empty result)",
                is_error=bool(result.get("is_error")),
            )
        except Exception as exc:
            logger.error("MCP tool %s error: %s", self.name, exc)
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"MCP tool error: {exc}",
                is_error=True,
            )


def create_mcp_tool_proxies() -> list[McpToolProxy]:
    """Create proxy tools for all connected MCP server tools."""
    tools = mcp_manager.get_all_tools()
    return [McpToolProxy(t) for t in tools]
