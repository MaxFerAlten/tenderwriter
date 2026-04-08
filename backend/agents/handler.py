"""Agent handler — executes agent turns with full tool-use loop.

Each agent turn may span multiple API calls when the model uses tools.
Tool execution is delegated to core.tool_runner for permission gating.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncIterator

from backend.agents.registry import agent_registry
from backend.core.streaming import StreamCollector
from backend.schemas.messages import Message, Role, ToolResultBlock
from backend.services.model_router import model_router
from backend.tools.registry import tool_registry

logger = logging.getLogger("tenderclaw.agents.handler")

MAX_AGENT_TURNS = 20


class AgentHandler:
    """Runs a full agentic turn for any registered agent, including tool loops."""

    async def execute_agent_turn(
        self,
        agent_name: str,
        messages: list[dict[str, Any]],
        system_override: str = "",
        model_override: str = "",
    ) -> AsyncIterator[dict[str, Any]]:
        agent = agent_registry.get(agent_name)
        model = model_override or agent.default_model
        system = system_override or agent.system_prompt

        available_tools = tool_registry.list_api_schemas()
        if agent.tools:
            available_tools = [t for t in available_tools if t["name"] in agent.tools]

        logger.info("Agent turn [%s] model=%s tools=%d", agent_name, model, len(available_tools))

        # Work on a mutable copy so we can append tool results
        turn_messages = list(messages)

        for turn in range(1, MAX_AGENT_TURNS + 1):
            message_id = f"msg_{uuid.uuid4().hex[:8]}"
            collector = StreamCollector(message_id=message_id, send=_noop_send)

            try:
                async for event in model_router.stream_message(
                    model=model,
                    messages=turn_messages,
                    system=system,
                    tools=available_tools or None,
                    max_tokens=8192,
                ):
                    await collector.process(event)
                    # Forward text deltas to caller
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield {"type": "assistant_text", "delta": delta.get("text", ""), "message_id": message_id}
            except Exception as exc:
                logger.error("Agent [%s] API error on turn %d: %s", agent_name, turn, exc)
                yield {"type": "error", "error": str(exc), "code": "api_error"}
                return

            if not collector.tool_uses or collector.stop_reason != "tool_use":
                break

            # Execute tools and append results for next turn
            tool_results = await _execute_agent_tools(collector.tool_uses, agent_name)
            for result_event in tool_results:
                yield result_event

            # Append assistant message + tool results to turn_messages
            assistant_blocks = _blocks_to_api(collector)
            turn_messages.append({"role": "assistant", "content": assistant_blocks})
            turn_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r["tool_use_id"],
                        "content": r["content"],
                        "is_error": r["is_error"],
                    }
                    for r in tool_results
                    if r.get("type") == "tool_result"
                ],
            })

        if turn >= MAX_AGENT_TURNS:
            logger.warning("Agent [%s] hit MAX_AGENT_TURNS (%d)", agent_name, MAX_AGENT_TURNS)


async def _execute_agent_tools(tool_uses: list, agent_name: str) -> list[dict[str, Any]]:
    """Execute tool uses for a sub-agent (no permission gating — agents are trusted)."""
    from backend.schemas.tools import ToolInput
    from backend.tools.base import ToolContext
    from backend.tools.execution import execute_tool

    results = []
    for tu in tool_uses:
        if not tool_registry.has(tu.name):
            results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "tool_name": tu.name,
                "content": f"Tool '{tu.name}' not found.",
                "is_error": True,
            })
            continue

        tool = tool_registry.get(tu.name)
        ctx = ToolContext(tool_use_id=tu.id)
        result = await execute_tool(
            tool,
            ToolInput(tool_use_id=tu.id, name=tu.name, input=tu.input),
            ctx,
        )
        results.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "tool_name": tu.name,
            "content": result.content,
            "is_error": result.is_error,
        })
    return results


def _blocks_to_api(collector: StreamCollector) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if collector.text_parts:
        blocks.append({"type": "text", "text": "".join(collector.text_parts)})
    for tu in collector.tool_uses:
        blocks.append({"type": "tool_use", "id": tu.id, "name": tu.name, "input": tu.input})
    return blocks


async def _noop_send(msg: dict[str, Any]) -> None:
    """No-op send — agent handler streams via yield, not WebSocket."""


# Module-level instance
agent_handler = AgentHandler()
