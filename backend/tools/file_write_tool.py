"""File write tool — create or overwrite files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.file_write")


class FileWriteTool(BaseTool):
    """Write content to a file, creating directories as needed."""

    name = "Write"
    description = (
        "Write content to a file. Creates the file if it doesn't exist, "
        "overwrites if it does. Creates parent directories automatically."
    )
    risk_level = RiskLevel.MEDIUM
    is_read_only = False
    concurrency_safe = False

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"File written successfully: {path} ({len(content)} bytes)",
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Error writing file: {exc}",
                is_error=True,
            )
