"""AST-grep tool — structural code search.

Allows searching for code patterns based on abstract syntax trees (ASTs).
Supports 25+ languages.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.ast_grep")


class AstGrepTool(BaseTool):
    """Search for structural code patterns using ast-grep."""

    name = "AstGrep"
    description = (
        "Search for code patterns using structural search (AST-grep). "
        "Useful for finding complex code constructs like 'functions without returns' "
        "or 'react components with specific hooks'. "
        "Supports CSS-like selectors or YAML rules."
    )
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "S-expression or selector pattern"},
                "path": {"type": "string", "description": "Directory to search in"},
                "language": {"type": "string", "description": "Language (ts, py, go, etc.)"},
                "rewrite": {"type": "string", "description": "Optional rewrite pattern (caution!)"},
            },
            "required": ["pattern"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = tool_input["pattern"]
        search_path = tool_input.get("path", context.working_directory)
        lang = tool_input.get("language", "")
        rewrite = tool_input.get("rewrite", "")

        cmd = ["ast-grep", "run", "--pattern", pattern]
        if lang:
            cmd.extend(["--lang", lang])
        if rewrite:
            # We don't want to actually rewrite in a read-only tool
            # But the user might want to see what it *would* look like
            cmd.extend(["--rewrite", rewrite, "--interactive", "false"])
        
        cmd.append(search_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            
            output = (stdout or b"").decode("utf-8", errors="replace").strip()
            err_output = (stderr or b"").decode("utf-8", errors="replace").strip()

            if not output and not err_output:
                return ToolResult(tool_use_id=context.tool_use_id, content="No matches found.")

            combined = output + ("\n" + err_output if err_output else "")
            return ToolResult(tool_use_id=context.tool_use_id, content=combined)

        except FileNotFoundError:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content="ast-grep binary not found. Install with: npm install -g @ast-grep/cli",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"AstGrep execution failed: {exc}",
                is_error=True,
            )
