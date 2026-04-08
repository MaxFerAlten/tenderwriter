"""File read tool — read file contents with line numbers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.file_read")

MAX_LINES = 2000


class FileReadTool(BaseTool):
    """Read a file and return its contents with line numbers."""

    name = "Read"
    description = (
        "Read a file from the filesystem. Returns contents with line numbers. "
        "Supports offset and limit for large files."
    )
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (1-based)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                    "default": MAX_LINES,
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        offset = max(tool_input.get("offset", 1), 1)
        limit = min(tool_input.get("limit", MAX_LINES), MAX_LINES)

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        if not path.exists():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"File does not exist: {path}",
                is_error=True,
            )

        if not path.is_file():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Not a file: {path}",
                is_error=True,
            )

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            total = len(lines)
            selected = lines[offset - 1 : offset - 1 + limit]

            numbered = "\n".join(
                f"{offset + i}\t{line}" for i, line in enumerate(selected)
            )

            header = f"File: {path} ({total} lines total)"
            if offset > 1 or len(selected) < total:
                header += f", showing lines {offset}-{offset + len(selected) - 1}"

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"{header}\n{numbered}",
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Error reading file: {exc}",
                is_error=True,
            )
