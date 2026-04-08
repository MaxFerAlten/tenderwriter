"""Hook Dispatcher — minimal integration point for Wave 2.

This module exposes a lightweight API to dispatch lifecycle hooks through
the central hook_registry.
"""

from __future__ import annotations

from typing import Any

from hooks.engine import hook_registry
from backend.schemas.hooks import HookPoint, HookEvent, HookResult


class HookDispatcher:
    """Dispatch hooks for a given lifecycle point."""

    async def dispatch(
        self,
        point: HookPoint,
        data: dict[str, Any],
        session_id: str = "",
    ) -> HookResult:
        event = HookEvent(point=point, data=data, session_id=session_id)
        return await hook_registry.run_hooks(point, event)


# Global singleton for convenience
hook_dispatcher = HookDispatcher()
