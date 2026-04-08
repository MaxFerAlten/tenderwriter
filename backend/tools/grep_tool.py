"""Grep tool — search file contents using regex patterns."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.grep")

MAX_MATCHES = 250


class GrepTool(BaseTool):
    """Search for regex patterns in file contents."""

    name = "Grep"
    description = (
        "Search for a regex pattern in file contents. "
        "Supports filtering by file glob and case-insensitive search."
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
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in",
                },
                "glob": {
                    "type": "string",
                    "description": "Glob to filter files (e.g., '*.py')",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive search",
                    "default": False,
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "default": "files_with_matches",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        pattern_str = tool_input.get("pattern", "")
        search_path = tool_input.get("path", context.working_directory) or "."
        file_glob = tool_input.get("glob", "**/*")
        case_insensitive = tool_input.get("case_insensitive", False)
        output_mode = tool_input.get("output_mode", "files_with_matches")

        base = Path(search_path)
        if not base.is_absolute():
            base = Path(context.working_directory) / base

        flags = re.IGNORECASE if case_insensitive else 0

        try:
            regex = re.compile(pattern_str, flags)
        except re.error as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Invalid regex: {exc}",
                is_error=True,
            )

        results: list[str] = []
        match_count = 0

        try:
            files = sorted(base.glob(file_glob)) if base.is_dir() else [base]

            for file_path in files:
                if not file_path.is_file():
                    continue

                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except (OSError, UnicodeDecodeError):
                    continue

                for line_num, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        match_count += 1
                        if match_count > MAX_MATCHES:
                            break

                        if output_mode == "content":
                            results.append(f"{file_path}:{line_num}: {line}")
                        elif output_mode == "files_with_matches":
                            file_str = str(file_path)
                            if file_str not in results:
                                results.append(file_str)
                        elif output_mode == "count":
                            pass  # Count only

                if match_count > MAX_MATCHES:
                    break

            if output_mode == "count":
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content=f"{match_count} matches found",
                )

            if not results:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content="No matches found",
                )

            output = "\n".join(results[:MAX_MATCHES])
            if match_count > MAX_MATCHES:
                output += f"\n... truncated ({match_count} total matches)"

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=output,
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Grep error: {exc}",
                is_error=True,
            )
