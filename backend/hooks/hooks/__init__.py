"""TenderClaw hooks package."""

from hooks.registry import (
    BaseHook,
    HookContext,
    HookEvent,
    HookRegistry,
    HookResult,
    hook,
)

__all__ = [
    "BaseHook",
    "HookContext",
    "HookEvent",
    "HookRegistry",
    "HookResult",
    "hook",
]
