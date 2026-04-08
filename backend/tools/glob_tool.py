"""Glob tool — fast file pattern matching."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.glob")

MAX_RESULTS = 500


class GlobTool(BaseTool):
    """Find files matching a glob pattern."""

    name = "Glob"
    description = (
        "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts'). "
        "Returns matching file paths sorted by modification time."
    )
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files against",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in (default: working directory)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        pattern = tool_input.get("pattern", "")
        search_path = tool_input.get("path", context.working_directory) or "."

        base = Path(search_path)
        if not base.is_absolute():
            base = Path(context.working_directory) / base

        if not base.exists():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Directory does not exist: {base}",
                is_error=True,
            )

        try:
            matches = sorted(
                base.glob(pattern),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )

            if not matches:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content=f"No files matched: {pattern}",
                )

            limited = matches[:MAX_RESULTS]
            lines = [str(p) for p in limited]
            result = "\n".join(lines)

            if len(matches) > MAX_RESULTS:
                result += f"\n... and {len(matches) - MAX_RESULTS} more"

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=result,
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Glob error: {exc}",
                is_error=True,
            )
