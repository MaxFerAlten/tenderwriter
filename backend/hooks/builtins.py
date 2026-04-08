"""Built-in Hooks — Common hook patterns and core hooks for TenderClaw."""

from __future__ import annotations

import asyncio
import json
import structlog
from typing import Any

from hooks.engine import hook_registry
from hooks.types import (
    HookEventType,
    HookEventData,
    HookResponse,
    HookConfig,
    SyncHookResponse,
)


logger = structlog.get_logger()


async def use_remote_session(event: HookEventData) -> HookResponse:
    """Remote session hook - delegates session handling to remote service."""
    session_id = event.get("session_id")
    
    logger.info("useRemoteSession hook triggered", session_id=session_id)
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "remote_session": True,
            "session_id": session_id,
            "delegated": True,
        },
    )


async def use_swarm_initialization(event: HookEventData) -> HookResponse:
    """Swarm initialization hook - sets up multi-agent environment."""
    logger.info("useSwarmInitialization hook triggered")
    
    return HookResponse(
        handled=True,
        modified=True,
        data={
            "swarm_mode": True,
            "agent_count": 1,
            "initialized": True,
        },
    )


async def pre_tool_use_logger(event: HookEventData) -> HookResponse:
    """Log tool usage before execution."""
    tool_name = event.get("tool_name", "unknown")
    tool_args = event.get("tool_args", {})
    
    logger.info(
        "PreToolUse hook triggered",
        tool=tool_name,
        args=tool_args,
        session_id=event.get("session_id"),
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={"tool_name": tool_name, "logged": True},
    )


async def post_tool_use_logger(event: HookEventData) -> HookResponse:
    """Log tool usage after execution."""
    tool_name = event.get("tool_name", "unknown")
    tool_result = event.get("tool_result")
    
    logger.info(
        "PostToolUse hook triggered",
        tool=tool_name,
        session_id=event.get("session_id"),
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "tool_name": tool_name,
            "result_logged": True,
            "has_result": tool_result is not None,
        },
    )


async def session_start_logger(event: HookEventData) -> HookResponse:
    """Log session start."""
    session_id = event.get("session_id")
    user_id = event.get("user_id")
    
    logger.info(
        "SessionStart hook triggered",
        session_id=session_id,
        user_id=user_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "session_id": session_id,
            "user_id": user_id,
            "logged": True,
        },
    )


async def user_prompt_logger(event: HookEventData) -> HookResponse:
    """Log user prompt submission."""
    prompt = event.get("prompt", "")
    session_id = event.get("session_id")
    
    logger.info(
        "UserPromptSubmit hook triggered",
        session_id=session_id,
        prompt_length=len(prompt),
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "prompt_length": len(prompt),
            "logged": True,
        },
    )


async def permission_request_handler(event: HookEventData) -> SyncHookResponse:
    """Handle permission requests."""
    permission_request = event.get("permission_request", "unknown")
    session_id = event.get("session_id")
    
    logger.info(
        "PermissionRequest hook triggered",
        permission=permission_request,
        session_id=session_id,
    )
    
    return SyncHookResponse(
        handled=True,
        modified=False,
        block=False,
        data={
            "permission_request": permission_request,
            "auto_approved": False,
        },
    )


async def permission_denied_handler(event: HookEventData) -> HookResponse:
    """Handle permission denied events."""
    permission_request = event.get("permission_request", "unknown")
    session_id = event.get("session_id")
    
    logger.warning(
        "PermissionDenied hook triggered",
        permission=permission_request,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "permission_request": permission_request,
            "denied": True,
            "logged": True,
        },
    )


async def elicitation_handler(event: HookEventData) -> HookResponse:
    """Handle elicitation events."""
    elicitation_type = event.get("elicitation_type", "unknown")
    session_id = event.get("session_id")
    
    logger.info(
        "Elicitation hook triggered",
        type=elicitation_type,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "elicitation_type": elicitation_type,
            "handled": True,
        },
    )


async def cwd_changed_handler(event: HookEventData) -> HookResponse:
    """Handle working directory changes."""
    cwd = event.get("cwd", "")
    session_id = event.get("session_id")
    
    logger.info(
        "CwdChanged hook triggered",
        cwd=cwd,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "cwd": cwd,
            "logged": True,
        },
    )


async def file_changed_handler(event: HookEventData) -> HookResponse:
    """Handle file change events."""
    file_path = event.get("file_path", "")
    session_id = event.get("session_id")
    
    logger.info(
        "FileChanged hook triggered",
        file_path=file_path,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "file_path": file_path,
            "logged": True,
        },
    )


async def worktree_create_handler(event: HookEventData) -> HookResponse:
    """Handle worktree creation events."""
    worktree_name = event.get("worktree_name", "")
    session_id = event.get("session_id")
    
    logger.info(
        "WorktreeCreate hook triggered",
        worktree_name=worktree_name,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "worktree_name": worktree_name,
            "logged": True,
        },
    )


async def subagent_start_handler(event: HookEventData) -> HookResponse:
    """Handle subagent start events."""
    subagent_name = event.get("subagent_name", "unknown")
    session_id = event.get("session_id")
    
    logger.info(
        "SubagentStart hook triggered",
        subagent_name=subagent_name,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "subagent_name": subagent_name,
            "logged": True,
        },
    )


async def setup_handler(event: HookEventData) -> HookResponse:
    """Handle setup events."""
    session_id = event.get("session_id")
    
    logger.info(
        "Setup hook triggered",
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=True,
        data={
            "setup_complete": True,
            "environment_ready": True,
        },
    )


async def post_tool_failure_handler(event: HookEventData) -> HookResponse:
    """Handle tool execution failures."""
    tool_name = event.get("tool_name", "unknown")
    error = event.get("error", "unknown")
    session_id = event.get("session_id")
    
    logger.error(
        "PostToolUseFailure hook triggered",
        tool=tool_name,
        error=error,
        session_id=session_id,
    )
    
    return HookResponse(
        handled=True,
        modified=False,
        data={
            "tool_name": tool_name,
            "error": error,
            "logged": True,
        },
    )


def register_builtin_hooks() -> None:
    """Register all built-in hooks with the registry."""
    default_config = HookConfig()
    
    hook_registry.register(
        name="useRemoteSession",
        event_type=HookEventType.SESSION_START,
        handler=use_remote_session,
        config=default_config,
        description="Delegates session handling to remote service",
    )
    
    hook_registry.register(
        name="useSwarmInitialization",
        event_type=HookEventType.SETUP,
        handler=use_swarm_initialization,
        config=default_config,
        description="Initializes multi-agent swarm mode",
    )
    
    hook_registry.register(
        name="preToolLogger",
        event_type=HookEventType.PRE_TOOL_USE,
        handler=pre_tool_use_logger,
        config=default_config,
        description="Logs tool usage before execution",
    )
    
    hook_registry.register(
        name="postToolLogger",
        event_type=HookEventType.POST_TOOL_USE,
        handler=post_tool_use_logger,
        config=default_config,
        description="Logs tool usage after execution",
    )
    
    hook_registry.register(
        name="sessionLogger",
        event_type=HookEventType.SESSION_START,
        handler=session_start_logger,
        config=default_config,
        description="Logs session start events",
    )
    
    hook_registry.register(
        name="promptLogger",
        event_type=HookEventType.USER_PROMPT_SUBMIT,
        handler=user_prompt_logger,
        config=default_config,
        description="Logs user prompt submissions",
    )
    
    hook_registry.register(
        name="permissionRequestHandler",
        event_type=HookEventType.PERMISSION_REQUEST,
        handler=permission_request_handler,
        config=default_config,
        description="Handles permission requests",
    )
    
    hook_registry.register(
        name="permissionDeniedHandler",
        event_type=HookEventType.PERMISSION_DENIED,
        handler=permission_denied_handler,
        config=default_config,
        description="Handles permission denied events",
    )
    
    hook_registry.register(
        name="elicitationHandler",
        event_type=HookEventType.ELICITATION,
        handler=elicitation_handler,
        config=default_config,
        description="Handles elicitation events",
    )
    
    hook_registry.register(
        name="cwdChangedHandler",
        event_type=HookEventType.CWD_CHANGED,
        handler=cwd_changed_handler,
        config=default_config,
        description="Handles working directory changes",
    )
    
    hook_registry.register(
        name="fileChangedHandler",
        event_type=HookEventType.FILE_CHANGED,
        handler=file_changed_handler,
        config=default_config,
        description="Handles file change events",
    )
    
    hook_registry.register(
        name="worktreeCreateHandler",
        event_type=HookEventType.WORKTREE_CREATE,
        handler=worktree_create_handler,
        config=default_config,
        description="Handles worktree creation events",
    )
    
    hook_registry.register(
        name="subagentStartHandler",
        event_type=HookEventType.SUBAGENT_START,
        handler=subagent_start_handler,
        config=default_config,
        description="Handles subagent start events",
    )
    
    hook_registry.register(
        name="setupHandler",
        event_type=HookEventType.SETUP,
        handler=setup_handler,
        config=default_config,
        description="Handles setup events",
    )
    
    hook_registry.register(
        name="postToolFailureHandler",
        event_type=HookEventType.POST_TOOL_USE_FAILURE,
        handler=post_tool_failure_handler,
        config=default_config,
        description="Handles tool execution failures",
    )
