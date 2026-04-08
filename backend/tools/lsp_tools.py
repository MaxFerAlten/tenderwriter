"""LSP tools — Language Server Protocol integration for code intelligence.

Inspired by oh-my-openagent's LSP tools. Provides goto-definition,
find-references, rename, and diagnostics via subprocess calls to
language-specific LSP servers.

Phase 2: Uses subprocess fallback (ripgrep/ctags) when no LSP server available.
Phase 3+: Full LSP client integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.lsp")


class LspGotoDefinitionTool(BaseTool):
    """Find the definition of a symbol."""

    name = "LspGotoDefinition"
    description = (
        "Find the definition of a symbol (function, class, variable). "
        "Uses grep-based fallback when no LSP server is available."
    )
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to find definition of"},
                "path": {"type": "string", "description": "Directory to search in"},
                "language": {"type": "string", "description": "Language hint (python, typescript, etc.)"},
            },
            "required": ["symbol"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        symbol = tool_input["symbol"]
        search_path = tool_input.get("path", context.working_directory)
        lang = tool_input.get("language", "")

        patterns = _definition_patterns(symbol, lang)
        results = await _grep_patterns(patterns, search_path)

        if not results:
            return ToolResult(tool_use_id=context.tool_use_id, content=f"No definition found for: {symbol}")

        return ToolResult(tool_use_id=context.tool_use_id, content="\n".join(results[:20]))


class LspFindReferencesTool(BaseTool):
    """Find all references to a symbol."""

    name = "LspFindReferences"
    description = "Find all references to a symbol across the codebase."
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol name to find references of"},
                "path": {"type": "string", "description": "Directory to search in"},
            },
            "required": ["symbol"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        symbol = tool_input["symbol"]
        search_path = tool_input.get("path", context.working_directory)

        results = await _grep_patterns([rf"\b{re.escape(symbol)}\b"], search_path)

        if not results:
            return ToolResult(tool_use_id=context.tool_use_id, content=f"No references found for: {symbol}")

        header = f"Found {len(results)} reference(s) for '{symbol}':"
        return ToolResult(tool_use_id=context.tool_use_id, content=header + "\n" + "\n".join(results[:50]))


class LspDiagnosticsTool(BaseTool):
    """Run diagnostics (lint/typecheck) on a file or project."""

    name = "LspDiagnostics"
    description = (
        "Run language-specific diagnostics (lint, typecheck) on files. "
        "Supports Python (ruff/mypy), TypeScript (tsc), and more."
    )
    risk_level = RiskLevel.NONE
    is_read_only = True
    concurrency_safe = True

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "File or directory to check"},
                "tool": {
                    "type": "string",
                    "description": "Diagnostic tool (ruff, mypy, tsc, eslint). Auto-detected if omitted.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = tool_input["file_path"]
        diag_tool = tool_input.get("tool", "")

        path = Path(file_path)
        if not path.is_absolute():
            path = Path(context.working_directory) / path

        if not diag_tool:
            diag_tool = _detect_diagnostic_tool(path)

        commands: dict[str, list[str]] = {
            "ruff": ["ruff", "check", str(path), "--output-format=text"],
            "mypy": ["mypy", str(path), "--no-color-output"],
            "tsc": ["npx", "tsc", "--noEmit", "--pretty", "false"],
            "eslint": ["npx", "eslint", str(path), "--format=compact"],
        }

        cmd = commands.get(diag_tool)
        if not cmd:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Unknown diagnostic tool: {diag_tool}. Use: ruff, mypy, tsc, eslint",
                is_error=True,
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=context.working_directory,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = (stdout or b"").decode("utf-8", errors="replace")
            err_output = (stderr or b"").decode("utf-8", errors="replace")
            combined = (output + "\n" + err_output).strip()

            if not combined:
                combined = "No issues found."

            return ToolResult(tool_use_id=context.tool_use_id, content=combined)

        except FileNotFoundError:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Diagnostic tool '{diag_tool}' not found. Install it first.",
                is_error=True,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Diagnostics timed out after 30s",
                is_error=True,
            )


def _definition_patterns(symbol: str, lang: str) -> list[str]:
    """Generate regex patterns for definition search by language."""
    escaped = re.escape(symbol)
    patterns = [
        rf"(def|class|function|const|let|var|type|interface|enum)\s+{escaped}\b",
        rf"{escaped}\s*[:=]\s*(function|class|\()",
        rf"export\s+(default\s+)?(function|class|const|let|var|type|interface)\s+{escaped}\b",
    ]
    if lang in ("python", "py"):
        patterns.insert(0, rf"(def|class)\s+{escaped}\s*[\(:]")
    elif lang in ("typescript", "ts", "javascript", "js"):
        patterns.insert(0, rf"(function|class|const|let|var|type|interface|enum)\s+{escaped}\b")
    return patterns


async def _grep_patterns(patterns: list[str], search_path: str) -> list[str]:
    """Run grep with multiple patterns and return matching lines."""
    results: list[str] = []
    for pattern in patterns:
        try:
            proc = await asyncio.create_subprocess_exec(
                "rg", "--line-number", "--no-heading", "-e", pattern, search_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if stdout:
                lines = stdout.decode("utf-8", errors="replace").strip().splitlines()
                results.extend(lines)
        except (FileNotFoundError, asyncio.TimeoutError):
            pass
    return list(dict.fromkeys(results))  # Deduplicate preserving order


def _detect_diagnostic_tool(path: Path) -> str:
    """Auto-detect which diagnostic tool to use."""
    suffix = path.suffix.lower()
    if suffix in (".py", ".pyi"):
        return "ruff"
    if suffix in (".ts", ".tsx"):
        return "tsc"
    if suffix in (".js", ".jsx"):
        return "eslint"
    return "ruff"
