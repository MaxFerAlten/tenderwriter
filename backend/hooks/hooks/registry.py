"""Hook system for TenderClaw lifecycle events."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class HookEvent(Enum):
    """Hook event types."""

    SESSION_CREATED = "session.created"
    SESSION_DELETED = "session.deleted"
    SESSION_IDLE = "session.idle"
    SESSION_ERROR = "session.error"
    
    MESSAGE_RECEIVED = "message.received"
    MESSAGE_SENT = "message.sent"
    MESSAGE_TRANSFORM = "message.transform"
    
    TOOL_BEFORE = "tool.before"
    TOOL_AFTER = "tool.after"
    TOOL_ERROR = "tool.error"
    
    CONTEXT_INJECT = "context.inject"
    CONTEXT_COMPACT = "context.compact"
    
    PARAMS_SET = "params.set"
    
    KEYWORD_DETECTED = "keyword.detected"
    MODE_ACTIVATED = "mode.activated"
    MODE_DEACTIVATED = "mode.deactivated"


@dataclass
class HookContext:
    """Context passed to hooks."""
    event: HookEvent
    session_id: str | None = None
    message: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def set(self, key: str, value: Any) -> None:
        """Set metadata value."""
        self.metadata[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get metadata value."""
        return self.metadata.get(key, default)


class HookResult:
    """Result from a hook execution."""
    
    def __init__(
        self,
        handled: bool = False,
        modified: bool = False,
        modified_content: str | None = None,
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        self.handled = handled
        self.modified = modified
        self.modified_content = modified_content
        self.metadata = metadata or {}
        self.error = error


class BaseHook(ABC):
    """Base class for hooks."""

    def __init__(self, name: str, events: list[HookEvent] | None = None):
        self.name = name
        self.events = events or []
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def execute(self, context: HookContext) -> HookResult:
        """Execute the hook."""
        pass

    async def before_execute(self, context: HookContext) -> None:
        """Called before execution."""
        pass

    async def after_execute(self, context: HookContext, result: HookResult) -> None:
        """Called after execution."""
        pass


class HookRegistry:
    """Registry for all hooks."""

    _hooks: dict[HookEvent, list[type[BaseHook]]] = {}
    _instances: dict[str, BaseHook] = {}

    @classmethod
    def register(cls, events: list[HookEvent] | None = None):
        """Decorator to register a hook class."""
        def decorator(hook_class: type[BaseHook]):
            hook_name = hook_class.__name__
            hook_events = events or []
            cls._hooks[hook_class] = {"events": hook_events, "class": hook_class}
            return hook_class
        return decorator

    @classmethod
    def get_hook(cls, name: str) -> BaseHook | None:
        """Get a hook instance by name."""
        return cls._instances.get(name)

    @classmethod
    def get_hooks_for_event(cls, event: HookEvent) -> list[BaseHook]:
        """Get all hooks registered for an event."""
        hooks = []
        for hook_class, info in cls._hooks.items():
            if event in info["events"]:
                hook_name = hook_class.__name__
                if hook_name not in cls._instances:
                    cls._instances[hook_name] = info["class"]()
                hooks.append(cls._instances[hook_name])
        return hooks

    @classmethod
    async def emit(cls, event: HookEvent, context: HookContext) -> HookResult:
        """Emit an event and run all registered hooks."""
        hooks = cls.get_hooks_for_event(event)
        
        combined_result = HookResult()
        for hook in hooks:
            try:
                await hook.before_execute(context)
                result = await hook.execute(context)
                
                if result.modified and result.modified_content:
                    combined_result.modified = True
                    combined_result.modified_content = result.modified_content
                    
                if result.handled:
                    combined_result.handled = True
                    
                combined_result.metadata.update(result.metadata)
                
                await hook.after_execute(context, result)
            except Exception as e:
                hook.logger.error(f"Hook {hook.name} error: {e}")
                combined_result.error = str(e)
                
        return combined_result


def hook(*events: HookEvent):
    """Shorthand decorator for hook registration."""
    return HookRegistry.register(list(events))
