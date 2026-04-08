"""Hashline Edit tool — content-hash anchored editing.

Inspired by oh-my-openagent's hashline system (oh-my-pi by Can Boluk).
Every line is tagged with a short hash of its content. Edits reference
the hash to prevent stale-line errors when files change between read and edit.

Success rate improvement: 6.7% -> 68.3% on noisy models.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.hashline_edit")

HASH_LENGTH = 4  # 4-char hash per line (e.g., "VK3a")


def compute_line_hash(line: str) -> str:
    """Compute a short content hash for a single line."""
    digest = hashlib.md5(line.encode("utf-8")).hexdigest()
    return digest[:HASH_LENGTH].upper()


def hashline_read(file_path: Path, offset: int = 1, limit: int = 200) -> str:
    """Read a file with hashline annotations.

    Each line is formatted as: {line_num}#{hash}| {content}
    Example: 11#VK3A| function hello() {
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    selected = lines[offset - 1 : offset - 1 + limit]

    annotated = []
    for i, line in enumerate(selected):
        line_num = offset + i
        line_hash = compute_line_hash(line)
        annotated.append(f"{line_num}#{line_hash}| {line}")

    return "\n".join(annotated)


class HashlineEditTool(BaseTool):
    """Edit a file using hash-anchored line references.

    Lines are identified by line_number + content_hash.
    If the hash doesn't match, the edit is rejected (file has changed).
    """

    name = "HashlineEdit"
    description = (
        "Edit a file using content-hash anchored line references. "
        "Each line is identified by its number and a 4-char hash. "
        "If the hash doesn't match the current content, the edit is rejected. "
        "Use HashlineRead first to get line hashes."
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
                    "description": "Absolute path to the file",
                },
                "edits": {
                    "type": "array",
                    "description": "List of line edits to apply",
                    "items": {
                        "type": "object",
                        "properties": {
                            "line": {"type": "integer", "description": "Line number"},
                            "hash": {"type": "string", "description": "4-char content hash"},
                            "new_content": {"type": "string", "description": "New line content"},
                        },
                        "required": ["line", "hash", "new_content"],
                    },
                },
            },
            "required": ["file_path", "edits"],
        }

    async def execute(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        edits = tool_input.get("edits", [])

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
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()

            # Validate all hashes before applying any edits
            errors = []
            for edit in edits:
                line_num = edit["line"]
                expected_hash = edit["hash"].upper()

                if line_num < 1 or line_num > len(lines):
                    errors.append(f"Line {line_num}: out of range (file has {len(lines)} lines)")
                    continue

                actual_hash = compute_line_hash(lines[line_num - 1])
                if actual_hash != expected_hash:
                    errors.append(
                        f"Line {line_num}: hash mismatch (expected {expected_hash}, got {actual_hash}). "
                        f"File has changed since last read."
                    )

            if errors:
                return ToolResult(
                    tool_use_id=context.tool_use_id,
                    content="Hash validation failed:\n" + "\n".join(errors),
                    is_error=True,
                )

            # Apply edits (in reverse order to preserve line numbers)
            sorted_edits = sorted(edits, key=lambda e: e["line"], reverse=True)
            for edit in sorted_edits:
                lines[edit["line"] - 1] = edit["new_content"]

            path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Applied {len(edits)} hashline edit(s) to {path}",
            )

        except Exception as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=f"Hashline edit error: {exc}",
                is_error=True,
            )
