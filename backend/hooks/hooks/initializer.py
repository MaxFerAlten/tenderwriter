"""Hook initializer – bootstrap comprehensive Wave 2 hooks.

This module registers a full set of lifecycle hooks covering session, turn,
tool, message, and agent events. Each handler is intentionally minimal and
safe — it logs context without altering business logic.
"""

from __future__ import annotations

import logging
from typing import Any

from hooks.engine import hook_registry
from backend.schemas.hooks import HookPoint, HookTier, HookAction, HookEvent, HookResult

logger = logging.getLogger("tenderclaw.hooks.initializer")


def bootstrap_hooks() -> None:
    """Register all Wave 2 lifecycle hooks."""
    # --- Session hooks ---
    hook_registry.register(
        name="wave2_session_start",
        point=HookPoint.SESSION_START,
        handler=_h_session_start,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_session_end",
        point=HookPoint.SESSION_END,
        handler=_h_session_end,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_session_compact_before",
        point=HookPoint.SESSION_COMPACT_BEFORE,
        handler=_h_session_compact_before,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_session_compact_after",
        point=HookPoint.SESSION_COMPACT_AFTER,
        handler=_h_session_compact_after,
        tier=HookTier.CONTINUATION,
        priority=0,
    )

    # --- Turn hooks ---
    hook_registry.register(
        name="wave2_turn_start",
        point=HookPoint.TURN_START,
        handler=_h_turn_start,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_turn_end",
        point=HookPoint.TURN_END,
        handler=_h_turn_end,
        tier=HookTier.CONTINUATION,
        priority=0,
    )

    # --- Tool hooks ---
    hook_registry.register(
        name="wave2_tool_before",
        point=HookPoint.TOOL_BEFORE,
        handler=_h_tool_before,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_tool_after",
        point=HookPoint.TOOL_AFTER,
        handler=_h_tool_after,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_tool_error",
        point=HookPoint.TOOL_ERROR,
        handler=_h_tool_error,
        tier=HookTier.CONTINUATION,
        priority=0,
    )

    # --- Message hooks ---
    hook_registry.register(
        name="wave2_message_system_build",
        point=HookPoint.MESSAGE_SYSTEM_BUILD,
        handler=_h_message_system_build,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_message_user_before",
        point=HookPoint.MESSAGE_USER_BEFORE,
        handler=_h_message_user_before,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_message_assistant_after",
        point=HookPoint.MESSAGE_ASSISTANT_AFTER,
        handler=_h_message_assistant_after,
        tier=HookTier.CONTINUATION,
        priority=0,
    )

    # --- Agent hooks ---
    hook_registry.register(
        name="wave2_agent_delegate_before",
        point=HookPoint.AGENT_DELEGATE_BEFORE,
        handler=_h_agent_delegate_before,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_agent_delegate_after",
        point=HookPoint.AGENT_DELEGATE_AFTER,
        handler=_h_agent_delegate_after,
        tier=HookTier.CONTINUATION,
        priority=0,
    )
    hook_registry.register(
        name="wave2_agent_model_fallback",
        point=HookPoint.AGENT_MODEL_FALLBACK,
        handler=_h_agent_model_fallback,
        tier=HookTier.CONTINUATION,
        priority=0,
    )

    registered = len(hook_registry._hooks)
    logger.info("Wave 2 hooks bootstrap complete — %d hooks registered", registered)


# ---------------------------------------------------------------------------
# Session handlers
# ---------------------------------------------------------------------------

async def _h_session_start(event: HookEvent) -> HookResult:
    logger.debug("HOOK session:start sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_session_end(event: HookEvent) -> HookResult:
    logger.debug("HOOK session:end sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_session_compact_before(event: HookEvent) -> HookResult:
    logger.debug("HOOK session:compact:before sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_session_compact_after(event: HookEvent) -> HookResult:
    logger.debug("HOOK session:compact:after sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


# ---------------------------------------------------------------------------
# Turn handlers
# ---------------------------------------------------------------------------

async def _h_turn_start(event: HookEvent) -> HookResult:
    logger.debug("HOOK turn:start sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_turn_end(event: HookEvent) -> HookResult:
    logger.debug("HOOK turn:end sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def _h_tool_before(event: HookEvent) -> HookResult:
    tool_name = event.data.get("tool_name", "?")
    logger.debug("HOOK tool:before tool=%s sid=%s", tool_name, event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_tool_after(event: HookEvent) -> HookResult:
    tool_name = event.data.get("tool_name", "?")
    logger.debug("HOOK tool:after tool=%s sid=%s", tool_name, event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_tool_error(event: HookEvent) -> HookResult:
    tool_name = event.data.get("tool_name", "?")
    error_msg = event.data.get("error", "?")
    logger.warning("HOOK tool:error tool=%s sid=%s error=%s", tool_name, event.session_id, error_msg)
    return HookResult(action=HookAction.CONTINUE)


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

async def _h_message_system_build(event: HookEvent) -> HookResult:
    logger.debug("HOOK message:system:build sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_message_user_before(event: HookEvent) -> HookResult:
    logger.debug("HOOK message:user:before sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_message_assistant_after(event: HookEvent) -> HookResult:
    logger.debug("HOOK message:assistant:after sid=%s", event.session_id)
    return HookResult(action=HookAction.CONTINUE)


# ---------------------------------------------------------------------------
# Agent handlers
# ---------------------------------------------------------------------------

async def _h_agent_delegate_before(event: HookEvent) -> HookResult:
    agent = event.data.get("agent", "?")
    logger.debug("HOOK agent:delegate:before agent=%s sid=%s", agent, event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_agent_delegate_after(event: HookEvent) -> HookResult:
    agent = event.data.get("agent", "?")
    logger.debug("HOOK agent:delegate:after agent=%s sid=%s", agent, event.session_id)
    return HookResult(action=HookAction.CONTINUE)


async def _h_agent_model_fallback(event: HookEvent) -> HookResult:
    from_model = event.data.get("from_model", "?")
    to_model = event.data.get("to_model", "?")
    logger.info("HOOK agent:model:fallback from=%s to=%s sid=%s", from_model, to_model, event.session_id)
    return HookResult(action=HookAction.CONTINUE)
