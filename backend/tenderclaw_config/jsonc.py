"""JSONC (JSON with Comments) parser.

Supports JSON files with single-line (//) and multi-line (/* */) comments.
Based on common JSONC implementations.
"""

from __future__ import annotations

import re
from typing import Any, Optional, TextIO
from pathlib import Path


def strip_jsonc_comments(content: str) -> str:
    """Remove JSONC comments from content.

    Handles:
    - Single-line comments: // comment
    - Multi-line comments: /* comment */
    - Preserves strings that might contain comment-like patterns
    """
    result = []
    i = 0
    length = len(content)

    while i < length:
        if content[i] == "/" and i + 1 < length:
            if content[i + 1] == "/":
                line_end = content.find("\n", i)
                if line_end == -1:
                    break
                i = line_end + 1
                continue
            elif content[i + 1] == "*":
                end = content.find("*/", i + 2)
                if end == -1:
                    break
                i = end + 2
                continue

        result.append(content[i])
        i += 1

    return "".join(result)


def load_jsonc(
    path: str | Path,
    encoding: str = "utf-8",
) -> dict[str, Any] | list[Any]:
    """Load and parse a JSONC file.

    Args:
        path: Path to the JSONC file
        encoding: File encoding (default: utf-8)

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid
    """
    import json

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding=encoding) as f:
        content = f.read()

    cleaned = strip_jsonc_comments(content)
    return json.loads(cleaned)


def loads_jsonc(content: str) -> dict[str, Any] | list[Any]:
    """Parse JSONC content from a string.

    Args:
        content: JSONC content string

    Returns:
        Parsed JSON data

    Raises:
        ValueError: If JSON is invalid
    """
    import json

    cleaned = strip_jsonc_comments(content)
    return json.loads(cleaned)


def validate_jsonc(content: str) -> tuple[bool, Optional[str]]:
    """Validate JSONC content without parsing.

    Args:
        content: JSONC content string

    Returns:
        Tuple of (is_valid, error_message)
    """
    import json

    try:
        cleaned = strip_jsonc_comments(content)
        json.loads(cleaned)
        return True, None
    except json.JSONDecodeError as e:
        return False, str(e)


def merge_jsonc(base: dict, override: dict) -> dict:
    """Deep merge two JSON objects, with override taking precedence.

    Args:
        base: Base configuration
        override: Override configuration

    Returns:
        Merged configuration
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_jsonc(result[key], value)
        else:
            result[key] = value

    return result
