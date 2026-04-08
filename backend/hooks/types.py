"""Hook Types — Type definitions for TenderClaw advanced hook system."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable
from pydantic import BaseModel, Field


class HookEventType(str, Enum):
    """All available hook event types in TenderClaw."""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    SESSION_START = "SessionStart"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SETUP = "Setup"
    SUBAGENT_START = "SubagentStart"
    PERMISSION_DENIED = "PermissionDenied"
    PERMISSION_REQUEST = "PermissionRequest"
    ELICITATION = "Elicitation"
    CWD_CHANGED = "CwdChanged"
    FILE_CHANGED = "FileChanged"
    WORKTREE_CREATE = "WorktreeCreate"


class HookResponse(BaseModel):
    """Base hook response model."""
    hook_id: str | None = None
    handled: bool = False
    modified: bool = False
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SyncHookResponse(HookResponse):
    """Synchronous hook response."""
    block: bool = False
    message: str | None = None


class AsyncHookResponse(HookResponse):
    """Asynchronous hook response."""
    await_other_hooks: bool = True
    priority_boost: int = 0


class HookConfig(BaseModel):
    """Configuration for a hook."""
    timeout_ms: int = 5000
    retry_count: int = 0
    retry_delay_ms: int = 1000
    allow_parallel: bool = True
    permission_behavior: str = "default"
    system_message_injection: str | None = None
    enabled: bool = True


class HookMetadata(BaseModel):
    """Metadata for a registered hook."""
    id: str
    name: str
    event_type: HookEventType
    description: str | None = None
    config: HookConfig = Field(default_factory=HookConfig)
    registered_at: float | None = None
    call_count: int = 0
    last_called: float | None = None
    last_error: str | None = None


class HookEventData(BaseModel):
    """Standardized event data passed to hooks."""
    session_id: str | None = None
    user_id: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    tool_result: Any | None = None
    error: str | None = None
    cwd: str | None = None
    file_path: str | None = None
    worktree_name: str | None = None
    subagent_name: str | None = None
    prompt: str | None = None
    modified_prompt: str | None = None
    permission_request: str | None = None
    permission_granted: bool | None = None
    elicitation_type: str | None = None
    elicitation_options: list[str] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class RegisteredHook:
    """Represents a registered hook handler."""
    id: str
    name: str
    event_type: HookEventType
    handler: Callable[..., Awaitable[HookResponse] | HookResponse]
    config: HookConfig = field(default_factory=HookConfig)
    is_async: bool = True
    description: str | None = None


@dataclass
class HookExecutionResult:
    """Result of a hook execution."""
    hook_id: str
    success: bool
    response: HookResponse | None = None
    error: str | None = None
    duration_ms: float = 0.0


class PermissionBehavior(str, Enum):
    """Behavior options for permission hooks."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
    SKIP = "skip"


class SystemMessageAction(str, Enum):
    """Actions for system message injection."""
    PREPEND = "prepend"
    APPEND = "append"
    REPLACE = "replace"
