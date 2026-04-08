"""Tool execution engine — runs tools with error handling and hook integration."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Callable, Awaitable

from backend.schemas.tools import ToolInput, ToolResult
from backend.tools.base import BaseTool, ToolContext
from backend.tools.registry import ToolRegistry
from backend.utils.errors import ToolExecutionError

logger = logging.getLogger("tenderclaw.tools.execution")


async def execute_tool(
    tool: BaseTool,
    tool_input: ToolInput,
    context: ToolContext,
) -> ToolResult:
    """Execute a single tool with error handling."""
    try:
        result = await tool.execute(tool_input.input, context)
        return result
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool.name, exc)
        return ToolResult(
            tool_use_id=tool_input.tool_use_id,
            content=f"Error executing {tool.name}: {exc}\n{traceback.format_exc()}",
            is_error=True,
        )


async def execute_tools_concurrent(
    registry: ToolRegistry,
    tool_inputs: list[ToolInput],
    context: ToolContext,
) -> list[ToolResult]:
    """Execute multiple tools — read-only tools run concurrently, write tools sequentially.

    This mirrors Claude Code's partitionToolCalls pattern.
    """
    read_only: list[tuple[BaseTool, ToolInput]] = []
    write_tools: list[tuple[BaseTool, ToolInput]] = []

    for ti in tool_inputs:
        tool = registry.get(ti.name)
        if tool.concurrency_safe:
            read_only.append((tool, ti))
        else:
            write_tools.append((tool, ti))

    results: list[ToolResult] = []

    # Run read-only tools concurrently
    if read_only:
        concurrent_results = await asyncio.gather(
            *[execute_tool(tool, ti, context) for tool, ti in read_only],
            return_exceptions=False,
        )
        results.extend(concurrent_results)

    # Run write tools sequentially
    for tool, ti in write_tools:
        result = await execute_tool(tool, ti, context)
        results.append(result)

    return results
