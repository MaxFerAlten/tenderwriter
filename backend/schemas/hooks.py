"""Hook schemas — lifecycle hook definitions and events."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class HookPoint(str, Enum):
    """Lifecycle points where hooks can fire."""

    # Session lifecycle
    SESSION_START = "session:start"
    SESSION_END = "session:end"
    SESSION_COMPACT_BEFORE = "session:compact:before"
    SESSION_COMPACT_AFTER = "session:compact:after"

    # Turn lifecycle
    TURN_START = "turn:start"
    TURN_END = "turn:end"

    # Tool lifecycle
    TOOL_BEFORE = "tool:before"
    TOOL_AFTER = "tool:after"
    TOOL_ERROR = "tool:error"

    # Message lifecycle
    MESSAGE_SYSTEM_BUILD = "message:system:build"
    MESSAGE_USER_BEFORE = "message:user:before"
    MESSAGE_ASSISTANT_AFTER = "message:assistant:after"

    # Agent lifecycle
    AGENT_DELEGATE_BEFORE = "agent:delegate:before"
    AGENT_DELEGATE_AFTER = "agent:delegate:after"
    AGENT_MODEL_FALLBACK = "agent:model:fallback"


class HookTier(str, Enum):
    """Hook priority tiers."""

    CORE = "core"                # Always active, high priority
    CONTINUATION = "continuation"  # Session lifecycle
    SKILL = "skill"              # Domain-specific
    TRANSFORM = "transform"      # Message modification


class HookAction(str, Enum):
    """Result action from a hook handler."""

    CONTINUE = "continue"    # Proceed normally
    BAIL = "bail"            # Stop execution chain
    MODIFY = "modify"        # Proceed with modified data


class HookEvent(BaseModel):
    """Event passed to a hook handler."""

    point: HookPoint
    data: dict[str, Any] = {}
    session_id: str = ""


class HookResult(BaseModel):
    """Result returned by a hook handler."""

    action: HookAction = HookAction.CONTINUE
    data: dict[str, Any] = {}
    reason: str = ""


class HookConfig(BaseModel):
    """Configuration for enabling/disabling hooks."""

    disabled_hooks: list[str] = []
