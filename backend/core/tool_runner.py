"""Tool runner — executes tool uses from a conversation turn.

Handles permission gating (ASK → wait for WS response), tool execution,
and result collection. Kept separate from the main agentic loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable

from backend.hooks.dispatcher import hook_dispatcher
from backend.hooks.permissions import check_permission
from backend.schemas.hooks import HookPoint
from backend.schemas.messages import ToolResultBlock, ToolUseBlock
from backend.schemas.permissions import PermissionDecision, PermissionMode
from backend.schemas.tools import ToolInput, ToolResult
from backend.schemas.ws import WSPermissionRequest, WSToolResult
from backend.services.session_store import SessionData
from backend.tools.base import ToolContext
from backend.tools.execution import execute_tool
from backend.tools.registry import tool_registry
from backend.telemetry.tracing import get_tracer, SpanKind
from backend.telemetry.metrics import metrics as telemetry_metrics
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger("tenderclaw.core.tool_runner")

tracer = get_tracer("tenderclaw.tool_runner")

SendFn = Callable[[dict[str, Any]], Awaitable[None]]

PERMISSION_TIMEOUT_SECS = 120


async def run_tool_uses(
    tool_uses: list[ToolUseBlock],
    session: SessionData,
    message_id: str,
    send: SendFn,
) -> list[ToolResultBlock]:
    """Execute all tool uses for a turn, gating on permissions where needed."""
    results: list[ToolResultBlock] = []

    with tracer.start_as_current_span(
        "tool.execution.batch",
        kind=SpanKind.INTERNAL,
        attributes={
            "session_id": session.session_id,
            "tool_count": len(tool_uses),
            "tool_names": [tu.name for tu in tool_uses],
        },
    ) as batch_span:
        try:
            for tu in tool_uses:
                if session.should_abort:
                    break

                result = await _run_single(tu, session, message_id, send)
                results.append(ToolResultBlock(
                    tool_use_id=tu.id,
                    content=result.content,
                    is_error=result.is_error,
                ))
                await send(WSToolResult(
                    tool_use_id=tu.id,
                    tool_name=tu.name,
                    content=result.content,
                    is_error=result.is_error,
                ).model_dump())

            batch_span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            batch_span.set_status(Status(StatusCode.ERROR, str(exc)))
            batch_span.record_exception(exc)
            raise
    return results


async def _run_single(
    tu: ToolUseBlock,
    session: SessionData,
    message_id: str,
    send: SendFn,
) -> ToolResult:
    import time

    with tracer.start_as_current_span(
        f"tool.{tu.name}",
        kind=SpanKind.INTERNAL,
        attributes={
            "session_id": session.session_id,
            "tool_name": tu.name,
            "tool_use_id": tu.id,
            "model": session.model,
        },
    ) as span:
        tool_start = time.perf_counter()
        try:
            result = await _execute_tool_with_tracing(tu, session, message_id, send)
            duration_ms = (time.perf_counter() - tool_start) * 1000
            telemetry_metrics.record_response_time(duration_ms, {"tool_name": tu.name})
            telemetry_metrics.increment_tool_call(tu.name, success=not result.is_error)
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as exc:
            telemetry_metrics.increment_tool_call(tu.name, success=False)
            telemetry_metrics.increment_error("tool_execution", {"tool_name": tu.name})
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


async def _execute_tool_with_tracing(
    tu: ToolUseBlock,
    session: SessionData,
    message_id: str,
    send: SendFn,
) -> ToolResult:
    """Internal tool execution with dispatch hooks."""
    permission_mode = PermissionMode(
        session.model_config.get("permission_mode", PermissionMode.DEFAULT)
    )
    decision = check_permission(tu.name, tu.input, mode=permission_mode)

    if decision == PermissionDecision.DENY:
        logger.info("Tool %s denied by permission rules", tu.name)
        return ToolResult(
            tool_use_id=tu.id,
            content=f"Tool '{tu.name}' was denied by permission rules.",
            is_error=True,
        )

    if decision == PermissionDecision.ASK:
        approved = await _ask_user(tu, session, send)
        if not approved:
            return ToolResult(
                tool_use_id=tu.id,
                content=f"Tool '{tu.name}' was denied by the user.",
                is_error=True,
            )

    tool = tool_registry.get(tu.name)
    ctx = ToolContext(
        session_id=session.session_id,
        working_directory=session.working_directory,
        message_id=message_id,
        tool_use_id=tu.id,
        send=send,
    )

    await hook_dispatcher.dispatch(
        HookPoint.TOOL_BEFORE,
        data={"tool_name": tu.name, "tool_input": tu.input, "tool_use_id": tu.id},
        session_id=session.session_id,
    )
    try:
        result = await execute_tool(tool, ToolInput(tool_use_id=tu.id, name=tu.name, input=tu.input), ctx)
    except Exception as exc:
        await hook_dispatcher.dispatch(
            HookPoint.TOOL_ERROR,
            data={"tool_name": tu.name, "tool_input": tu.input, "error": str(exc)},
            session_id=session.session_id,
        )
        raise
    await hook_dispatcher.dispatch(
        HookPoint.TOOL_AFTER,
        data={"tool_name": tu.name, "tool_use_id": tu.id, "result": result.content, "is_error": result.is_error},
        session_id=session.session_id,
    )
    return result


async def _ask_user(tu: ToolUseBlock, session: SessionData, send: SendFn) -> bool:
    """Send a permission_request to the frontend and wait for the response."""
    tool = tool_registry.get(tu.name) if tool_registry.has(tu.name) else None
    risk = tool.risk_level.value if tool else "medium"

    event = session.register_permission_request(tu.id)
    await send(WSPermissionRequest(
        tool_use_id=tu.id,
        tool_name=tu.name,
        tool_input=tu.input,
        risk_level=risk,
    ).model_dump())

    try:
        await asyncio.wait_for(event.wait(), timeout=PERMISSION_TIMEOUT_SECS)
    except asyncio.TimeoutError:
        logger.warning("Permission request timed out for tool %s", tu.name)
        session.clear_permission(tu.id)
        return False

    decision = session.get_permission_decision(tu.id)
    session.clear_permission(tu.id)
    return decision == "approve"
