"""Hook initializer – bootstrap core hooks for Wave 2 MVP.

Registers a small set of hooks that log lifecycle events to demonstrate
integration of the hook system with runtime flow. This is intentionally simple
and safe — it does not alter business logic, only observability hooks.
"""

from __future__ import annotations

from hooks.engine import hook_registry
from backend.schemas.hooks import HookPoint, HookTier


def bootstrap_hooks() -> None:
    # Lightweight, observable hooks for Wave 2 MVP
    hook_registry.register(
        name="wave2_session_logger",
        point=HookPoint.SESSION_START,
        handler=_log_session_start,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_turn_logger",
        point=HookPoint.TURN_START,
        handler=_log_turn_start,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_tool_logger",
        point=HookPoint.TOOL_BEFORE,
        handler=_log_tool_before,
        tier=HookTier.CONTINUATION,
        priority=0,
    )


async def _log_session_start(event):
    return None


async def _log_turn_start(event):
    return None


async def _log_tool_before(event):
    return None
