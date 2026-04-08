"""Hook engine — priority-ordered lifecycle hook execution.

Hooks fire at defined lifecycle points (session, turn, tool, message).
They run in priority order, and a handler can bail out to stop the chain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from backend.schemas.hooks import (
    HookAction,
    HookEvent,
    HookPoint,
    HookResult,
    HookTier,
)

logger = logging.getLogger("tenderclaw.hooks.engine")

# Type alias for async hook handlers
HookHandler = Callable[[HookEvent], Awaitable[HookResult]]

# Priority values for each tier (lower = runs first)
_TIER_PRIORITY: dict[HookTier, int] = {
    HookTier.CORE: 0,
    HookTier.CONTINUATION: 100,
    HookTier.SKILL: 200,
    HookTier.TRANSFORM: 300,
}


@dataclass
class HookEntry:
    """A registered hook handler with metadata."""

    name: str
    point: HookPoint
    handler: HookHandler
    tier: HookTier = HookTier.SKILL
    priority: int = 0  # Within-tier priority (lower = earlier)

    @property
    def effective_priority(self) -> int:
        """Combined priority: tier base + within-tier offset."""
        return _TIER_PRIORITY.get(self.tier, 200) + self.priority


class HookRegistry:
    """Registry and runner for lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[HookEntry]] = {}

    def register(
        self,
        name: str,
        point: HookPoint,
        handler: HookHandler,
        tier: HookTier = HookTier.SKILL,
        priority: int = 0,
    ) -> None:
        """Register a hook handler for a lifecycle point.

        Args:
            name: Unique name for this hook.
            point: Lifecycle point to attach to.
            handler: Async callable receiving HookEvent, returning HookResult.
            tier: Priority tier (core > continuation > skill > transform).
            priority: Within-tier ordering (lower runs first).
        """
        entry = HookEntry(
            name=name,
            point=point,
            handler=handler,
            tier=tier,
            priority=priority,
        )

        if point not in self._hooks:
            self._hooks[point] = []
        self._hooks[point].append(entry)
        self._hooks[point].sort(key=lambda e: e.effective_priority)
        logger.debug("Hook registered: %s at %s (tier=%s)", name, point.value, tier.value)

    def unregister(self, name: str) -> None:
        """Remove all hooks with the given name."""
        for point, entries in self._hooks.items():
            self._hooks[point] = [e for e in entries if e.name != name]

    async def run_hooks(self, point: HookPoint, event: HookEvent) -> HookResult:
        """Run all hooks for a lifecycle point in priority order.

        If any hook returns BAIL, execution stops and that result is returned.
        If a hook returns MODIFY, its data is merged into the event for
        subsequent hooks.

        Returns:
            The last HookResult (or CONTINUE with empty data if no hooks ran).
        """
        entries = self._hooks.get(point, [])
        if not entries:
            return HookResult(action=HookAction.CONTINUE)

        last_result = HookResult(action=HookAction.CONTINUE)

        for entry in entries:
            try:
                result = await entry.handler(event)
            except Exception as exc:
                logger.error("Hook %s raised: %s", entry.name, exc)
                continue

            last_result = result

            if result.action == HookAction.BAIL:
                logger.info("Hook %s bailed at %s: %s", entry.name, point.value, result.reason)
                return result

            if result.action == HookAction.MODIFY:
                event.data.update(result.data)

        return last_result

    def list_hooks(self, point: HookPoint | None = None) -> list[str]:
        """List registered hook names, optionally filtered by point."""
        if point is not None:
            return [e.name for e in self._hooks.get(point, [])]
        return [e.name for entries in self._hooks.values() for e in entries]


# Module-level instance
hook_registry = HookRegistry()
