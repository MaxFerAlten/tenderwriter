"""Runtime permissions policy (Wave 1).

Wraps the existing hook permission checker to provide a runtime-friendly API.
"""

from __future__ import annotations

from typing import Any

from backend.hooks.permissions import check_permission
from backend.schemas.permissions import PermissionDecision


def can_invoke(tool_name: str, tool_input: dict[str, Any], mode: str | None = None) -> PermissionDecision:
    """Determine whether a tool can be invoked given a mode.

    This is a thin wrapper around the existing check_permission implementation.
    """
    return check_permission(tool_name, tool_input, mode=mode)
