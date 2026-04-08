"""Streaming helpers — parse model_router events into structured data."""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from backend.schemas.messages import TextBlock, TokenUsage, ToolUseBlock
from backend.schemas.ws import (
    WSAssistantText,
    WSAssistantThinking,
    WSToolUseStart,
)

logger = logging.getLogger("tenderclaw.core.streaming")

SendFn = Callable[[dict[str, Any]], Awaitable[None]]


class StreamCollector:
    """Collects streaming events from model_router into structured results."""

    def __init__(self, message_id: str, send: SendFn) -> None:
        self.message_id = message_id
        self.send = send
        self.text_parts: list[str] = []
        self.tool_uses: list[ToolUseBlock] = []
        self.stop_reason: str = "end_turn"
        self.usage: TokenUsage = TokenUsage()
        self._current_tool_id = ""
        self._current_tool_name = ""
        self._current_tool_json = ""

    async def process(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")

        if event_type == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "tool_use":
                self._current_tool_id = block.get("id", "")
                self._current_tool_name = block.get("name", "")
                self._current_tool_json = ""
                await self.send(WSToolUseStart(
                    tool_use_id=self._current_tool_id,
                    tool_name=self._current_tool_name,
                    message_id=self.message_id,
                ).model_dump())

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            dtype = delta.get("type", "")

            if dtype == "text_delta":
                text = delta.get("text", "")
                self.text_parts.append(text)
                await self.send(WSAssistantText(delta=text, message_id=self.message_id).model_dump())

            elif dtype == "thinking_delta":
                await self.send(WSAssistantThinking(
                    delta=delta.get("thinking", ""),
                    message_id=self.message_id,
                ).model_dump())

            elif dtype == "input_json_delta":
                self._current_tool_json += delta.get("partial_json", "")

        elif event_type == "content_block_stop":
            if self._current_tool_id:
                try:
                    parsed = json.loads(self._current_tool_json) if self._current_tool_json else {}
                except json.JSONDecodeError:
                    parsed = {}
                self.tool_uses.append(ToolUseBlock(
                    id=self._current_tool_id,
                    name=self._current_tool_name,
                    input=parsed,
                ))
                self._current_tool_id = ""
                self._current_tool_name = ""
                self._current_tool_json = ""

        elif event_type == "message_delta":
            self.stop_reason = event.get("delta", {}).get("stop_reason", "end_turn") or "end_turn"

        elif event_type == "usage":
            raw = event.get("usage", {})
            if isinstance(raw, TokenUsage):
                self.usage = raw
            elif isinstance(raw, dict):
                self.usage = TokenUsage(
                    input_tokens=raw.get("input_tokens", 0),
                    output_tokens=raw.get("output_tokens", 0),
                )

    def content_blocks(self) -> list[TextBlock | ToolUseBlock]:
        blocks: list[TextBlock | ToolUseBlock] = []
        if self.text_parts:
            blocks.append(TextBlock(text="".join(self.text_parts)))
        blocks.extend(self.tool_uses)
        return blocks
