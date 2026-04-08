"""Turn Protection for Compaction.

Ported from OpenClaw's compaction-safeguard.ts.
Preserves recent turns verbatim during summarization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.services.compaction.messages import AgentMessage, MessageRole


@dataclass
class TurnProtection:
    """Configuration for turn protection."""

    enabled: bool = True
    preserve_recent_turns: int = 3  # Preserve N recent user/assistant turns
    preserve_system: bool = True  # Always preserve system messages
    preserve_recent_tool_results: int = 5  # Keep recent tool results


def split_preserved_recent_turns(
    messages: List[AgentMessage],
    config: Optional[TurnProtection] = None,
) -> Tuple[List[AgentMessage], List[AgentMessage], Dict[str, Any]]:
    """Split messages into preserved and summarizable portions.

    Recent turns are preserved verbatim for continuity.
    Older history is summarized to save tokens.

    Args:
        messages: All messages
        config: Turn protection config

    Returns:
        Tuple of (preserved_messages, summarizable_messages, stats)
    """
    config = config or TurnProtection()
    stats: Dict[str, Any] = {
        "preserved_count": 0,
        "summarizable_count": 0,
        "preserved_turns": 0,
        "preserved_tool_results": 0,
    }

    if not config.enabled:
        return [], messages, stats

    preserved: List[AgentMessage] = []
    summarizable: List[AgentMessage] = []

    # Collect recent turns (from the end)
    recent_turns: List[AgentMessage] = []
    recent_tool_results: List[AgentMessage] = []
    turn_count = 0

    # Go backwards through messages
    for msg in reversed(messages):
        if msg.role == MessageRole.USER:
            if turn_count < config.preserve_recent_turns:
                recent_turns.append(msg)
                turn_count += 1
            else:
                summarizable.append(msg)
        elif msg.role == MessageRole.ASSISTANT:
            if turn_count < config.preserve_recent_turns:
                recent_turns.append(msg)
                turn_count += 1
            else:
                summarizable.append(msg)
        elif msg.role == MessageRole.TOOL_RESULT:
            if len(recent_tool_results) < config.preserve_recent_tool_results:
                recent_tool_results.append(msg)
            else:
                summarizable.append(msg)
        elif msg.role == MessageRole.SYSTEM:
            if config.preserve_system:
                preserved.append(msg)
            else:
                summarizable.append(msg)
        else:
            summarizable.append(msg)

    # Reverse to restore order
    recent_turns.reverse()
    recent_tool_results.reverse()

    # Combine preserved
    preserved.extend(recent_turns)
    preserved.extend(recent_tool_results)

    # Reverse summarizable to restore chronological order
    summarizable.reverse()

    # Update stats
    stats["preserved_count"] = len(preserved)
    stats["summarizable_count"] = len(summarizable)
    stats["preserved_turns"] = len([m for m in recent_turns if m.role in (MessageRole.USER, MessageRole.ASSISTANT)])
    stats["preserved_tool_results"] = len(recent_tool_results)

    return preserved, summarizable, stats


def format_preserved_turns(messages: List[AgentMessage]) -> str:
    """Format preserved turns as text for context."""
    if not messages:
        return ""

    lines = ["## Recent Context (verbatim)\n"]
    for msg in messages:
        if msg.role == MessageRole.USER:
            lines.append(f"User: {msg.content[:200]}")
        elif msg.role == MessageRole.ASSISTANT:
            if msg.content:
                lines.append(f"Assistant: {msg.content[:200]}")
            if msg.tool_calls:
                tc_names = [tc.name for tc in msg.tool_calls]
                lines.append(f"Assistant used tools: {', '.join(tc_names)}")
        elif msg.role == MessageRole.TOOL_RESULT:
            tool_name = msg.tool_name or "tool"
            content = (msg.tool_result_content or msg.content or "")[:100]
            lines.append(f"{tool_name}: {content}...")

    return "\n".join(lines)


def should_preserve_message(msg: AgentMessage, config: TurnProtection) -> bool:
    """Check if a message should be preserved based on config."""
    if not config.enabled:
        return False

    # System messages
    if msg.role == MessageRole.SYSTEM:
        return config.preserve_system

    # Tool results - check if recent
    if msg.role == MessageRole.TOOL_RESULT:
        # This is simplified; real implementation would track position
        return len(msg.tool_name or "") > 0

    return False
