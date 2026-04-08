"""Hashline Read tool — read files with content-hash line annotations.

Companion to HashlineEditTool. Returns lines tagged with hashes
that the edit tool uses for validation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext
from backend.tools.hashline_edit_tool import hashline_read

logger = logging.getLogger("tenderclaw.tools.hashline_read")


class HashlineReadTool(BaseTool):
    """Read a file with hashline annotations for later editing."""

    name = "HashlineRead"
    description = (
        "Read a file with content-hash annotations on each line. "
        "Format: {line_num}#{hash}| {content}. "
        "Use these hashes with HashlineEdit for safe editing."
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
                    "description": "Absolute path to the file",
                },
                "offset": {
                    "type": "integer",
                    "description": "Starting line number (1-based)",
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max lines to read",
                    "default": 200,
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
        limit = min(tool_input.get("limit", 200), 2000)

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        if not path.exists():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"File does not exist: {path}",
                is_error=True,
            )

        try:
            content = hashline_read(path, offset=offset, limit=limit)
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=content,
            )
        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Hashline read error: {exc}",
                is_error=True,
            )
