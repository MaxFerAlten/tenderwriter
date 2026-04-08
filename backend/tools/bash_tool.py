"""Bash tool — execute shell commands with sandboxing."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.bash")

MAX_OUTPUT_LENGTH = 50_000
DEFAULT_TIMEOUT_MS = 120_000


class BashTool(BaseTool):
    """Execute shell commands and return stdout/stderr."""

    name = "Bash"
    description = (
        "Execute a shell command and return its output. "
        "Use for running scripts, installing packages, git operations, etc."
    )
    risk_level = RiskLevel.HIGH
    is_read_only = False
    concurrency_safe = False

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds (max 600000)",
                    "default": DEFAULT_TIMEOUT_MS,
                },
            },
            "required": ["command"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        command = tool_input.get("command", "")
        timeout_ms = min(tool_input.get("timeout", DEFAULT_TIMEOUT_MS), 600_000)
        timeout_s = timeout_ms / 1000

        if not command.strip():
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content="Error: empty command",
                is_error=True,
            )

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.working_directory or None,
                env={**os.environ},
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_s,
            )

            output_parts: list[str] = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            if stderr:
                output_parts.append(stderr.decode("utf-8", errors="replace"))

            output = "\n".join(output_parts)
            if len(output) > MAX_OUTPUT_LENGTH:
                output = output[:MAX_OUTPUT_LENGTH] + "\n... (truncated)"

            exit_code = process.returncode or 0
            if exit_code != 0:
                output = f"Exit code: {exit_code}\n{output}"

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=output or "(no output)",
                is_error=exit_code != 0,
            )

        except asyncio.TimeoutError:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Command timed out after {timeout_s}s",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Failed to execute command: {exc}",
                is_error=True,
            )
