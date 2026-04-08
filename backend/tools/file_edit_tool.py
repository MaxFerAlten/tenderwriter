"""File edit tool — find-and-replace editing with exact string matching."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.file_edit")


class FileEditTool(BaseTool):
    """Edit a file by replacing an exact string with a new string."""

    name = "Edit"
    description = (
        "Perform exact string replacement in a file. "
        "The old_string must be unique in the file. "
        "Use replace_all=true to replace all occurrences."
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
                    "description": "Absolute path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default: false)",
                    "default": False,
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        replace_all = tool_input.get("replace_all", False)

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
            content = path.read_text(encoding="utf-8")
            count = content.count(old_string)

            if count == 0:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content=f"old_string not found in {path}",
                    is_error=True,
                )

            if count > 1 and not replace_all:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content=(
                        f"old_string found {count} times in {path}. "
                        "Provide a larger unique string or set replace_all=true."
                    ),
                    is_error=True,
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)

            path.write_text(new_content, encoding="utf-8")

            replacements = count if replace_all else 1
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Edited {path}: {replacements} replacement(s) made",
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Error editing file: {exc}",
                is_error=True,
            )
