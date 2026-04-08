"""Hook Engine — Core hook registry and execution engine."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Awaitable
from hooks.types import HookEventType, HookEventData, HookResponse, RegisteredHook


class HookRegistry:
    """Central registry for hook handlers."""

    def __init__(self):
        self._hooks: dict[HookEventType, list[RegisteredHook]] = {}

    def register(
        self,
        name: str,
        event_type: HookEventType,
        handler: Callable[..., Awaitable[HookResponse] | HookResponse],
        config=None,
        is_async: bool = True,
        description: str | None = None,
    ) -> str:
        """Register a hook handler."""
        hook_id = f"{name}_{event_type.value}_{id(handler)}"
        
        if config is None:
            from hooks.types import HookConfig
            config = HookConfig()
        
        hook = RegisteredHook(
            id=hook_id,
            name=name,
            event_type=event_type,
            handler=handler,
            config=config,
            is_async=is_async,
            description=description,
        )

        if event_type not in self._hooks:
            self._hooks[event_type] = []
        
        self._hooks[event_type].append(hook)
        return hook_id

    def unregister(self, hook_id: str) -> bool:
        """Unregister a hook by ID."""
        for hooks in self._hooks.values():
            for i, hook in enumerate(hooks):
                if hook.id == hook_id:
                    hooks.pop(i)
                    return True
        return False

    def get_hooks_for_event(self, event_type: HookEventType) -> list[RegisteredHook]:
        """Get all hooks registered for an event type."""
        return self._hooks.get(event_type, [])

    def get_all_hooks(self) -> dict[HookEventType, list[RegisteredHook]]:
        """Get all registered hooks organized by event type."""
        return self._hooks.copy()

    def clear(self) -> None:
        """Clear all registered hooks."""
        self._hooks.clear()


# Global singleton
hook_registry = HookRegistry()


async def run_hooks(event_type: HookEventType, event: HookEventData) -> HookResponse:
    """Run all hooks for a given event type and return aggregated response."""
    hooks = hook_registry.get_hooks_for_event(event_type)
    
    if not hooks:
        return HookResponse(handled=False)

    responses = []
    for hook in hooks:
        try:
            if asyncio.iscoroutinefunction(hook.handler):
                response = await hook.handler(event)
            else:
                response = hook.handler(event)
            responses.append(response)
        except Exception as e:
            responses.append(HookResponse(handled=True, error=str(e)))

    if responses:
        first = responses[0]
        modified_data = {}
        for r in responses:
            if r.modified and r.data:
                modified_data.update(r.data)
        
        return HookResponse(
            handled=True,
            modified=bool(modified_data),
            data=modified_data or first.data,
            error=first.error,
        )

    return HookResponse(handled=False)
