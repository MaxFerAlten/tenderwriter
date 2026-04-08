"""SuperpowerCommandTool — wraps a superpowers command as a callable TenderClaw tool.

When invoked by the model, the tool returns its command body as instruction text.
This surfaces the superpowers methodology to the model without needing the
full Claude Code CLI runtime.
"""

from __future__ import annotations

from typing import Any

from backend.tools.base import BaseTool, ToolResult


class SuperpowerCommandTool(BaseTool):
    """A tool that surfaces a superpowers command methodology to the model."""

    # BaseTool uses class-level str/bool attributes — set defaults here.
    risk_level = "low"
    is_read_only = True
    concurrency_safe = True

    def __init__(self, name: str, description: str, body: str) -> None:
        # Assign instance attributes so BaseTool.to_api_schema / to_spec
        # see the correct per-tool values.
        self.name = name
        self.description = description
        self._body = body

    # -----------------------------------------------------------------------
    # BaseTool abstract method — must be a plain method, NOT a @property.
    # BaseTool.to_api_schema() calls self.input_schema() with parentheses.
    # -----------------------------------------------------------------------
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "description": (
                        "Optional context to apply this command to "
                        "(e.g., task description, file path)."
                    ),
                },
            },
            "required": [],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: Any = None,
    ) -> ToolResult:
        """Return the command body as instruction text, optionally injecting context."""
        ctx = tool_input.get("context", "")
        content = f"Context: {ctx}\n\n{self._body}" if ctx else self._body
        return ToolResult(content=content, is_error=False)
