"""Message Types and Token Estimation.

Core message types and token counting utilities.
Based on OpenClaw's compaction.ts message handling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class MessageRole(str, Enum):
    """Message role types."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_USE = "toolUse"
    TOOL_RESULT = "toolResult"


@dataclass
class ToolCall:
    """A tool call from assistant message."""

    id: str
    name: str
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from tool execution."""

    tool_call_id: str
    content: str
    is_error: bool = False
    tool_name: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class AgentMessage:
    """A message in the conversation history."""

    role: MessageRole
    content: Union[str, List[Any]]
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_result_content: Optional[str] = None
    is_error: Optional[bool] = None
    stop_reason: Optional[str] = None
    thinking: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentMessage:
        """Create from dict."""
        role = MessageRole(data.get("role", "user"))
        
        # Handle tool calls
        tool_calls = None
        if "toolCalls" in data or "tool_calls" in data:
            tc_data = data.get("toolCalls") or data.get("tool_calls", [])
            tool_calls = [
                ToolCall(id=tc["id"], name=tc["name"], input=tc.get("input", {}))
                for tc in tc_data
            ]
        
        # Handle tool result
        tool_call_id = data.get("toolCallId") or data.get("tool_call_id")
        tool_name = data.get("toolName") or data.get("tool_name")
        tool_result_content = data.get("content", "")
        
        # Handle content as list (for tool results, images, etc.)
        content = data.get("content", "")
        if isinstance(content, list):
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "toolResult":
                        tool_result_content = block.get("content", "")
                        tool_call_id = block.get("toolCallId")
                        is_error = block.get("isError", False)
            content = "\n".join(text_parts) if text_parts else str(tool_result_content)
        
        return cls(
            role=role,
            content=str(content),
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result_content=str(tool_result_content) if tool_result_content else None,
            is_error=data.get("isError") or data.get("is_error"),
            stop_reason=data.get("stopReason") or data.get("stop_reason"),
            thinking=data.get("thinking"),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict."""
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        
        if self.tool_calls:
            result["toolCalls"] = [
                {"id": tc.id, "name": tc.name, "input": tc.input}
                for tc in self.tool_calls
            ]
        
        if self.tool_call_id:
            result["toolCallId"] = self.tool_call_id
        if self.tool_name:
            result["toolName"] = self.tool_name
        if self.tool_result_content is not None:
            result["content"] = self.tool_result_content
        if self.is_error is not None:
            result["isError"] = self.is_error
        if self.stop_reason:
            result["stopReason"] = self.stop_reason
        if self.thinking:
            result["thinking"] = self.thinking
            
        return result


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses a simple approximation: ~4 characters per token for English.
    For more accurate counting, integrate tiktoken or similar.
    """
    if not text:
        return 0
    # Rough approximation: average 4 chars per token
    return len(text) // 4 + len(text.split())


def estimate_message_tokens(message: AgentMessage) -> int:
    """Estimate token count for a message."""
    tokens = estimate_tokens(str(message.content))
    
    # Add overhead for role and structure
    tokens += 4  # Role tag
    
    if message.tool_calls:
        tokens += 4  # Tool calls overhead
        for tc in message.tool_calls:
            tokens += estimate_tokens(tc.name)
            tokens += estimate_tokens(str(tc.input))
    
    if message.tool_call_id:
        tokens += 4  # Tool result overhead
    
    if message.thinking:
        tokens += estimate_tokens(message.thinking)
    
    return tokens


def estimate_messages_tokens(messages: List[AgentMessage]) -> int:
    """Estimate total tokens for messages.

    SECURITY: Does not include toolResult.details to prevent
    leaking untrusted payloads.
    """
    safe_messages = strip_tool_result_details(messages)
    return sum(estimate_message_tokens(m) for m in safe_messages)


def strip_tool_result_details(messages: List[AgentMessage]) -> List[AgentMessage]:
    """Strip tool result details for security.

    toolResult.details can contain untrusted/verbose payloads
    that should not be included in LLM-facing compaction.
    """
    result = []
    for msg in messages:
        if msg.role != MessageRole.TOOL_RESULT:
            result.append(msg)
            continue
        
        # Create a copy without details for security
        clean_msg = AgentMessage(
            role=msg.role,
            content=msg.content,
            tool_call_id=msg.tool_call_id,
            tool_name=msg.tool_name,
            tool_result_content=msg.tool_result_content,
            is_error=msg.is_error,
            metadata={},  # Strip metadata for security
        )
        result.append(clean_msg)
    
    return result


def extract_tool_calls(message: AgentMessage) -> List[ToolCall]:
    """Extract tool calls from assistant message."""
    if message.role != MessageRole.ASSISTANT:
        return []
    return message.tool_calls or []


def split_messages_by_token_share(
    messages: List[AgentMessage],
    parts: int = 4,
    max_context_tokens: int = 16000,
) -> List[List[AgentMessage]]:
    """Split messages into roughly equal token chunks.

    Keeps tool_use/tool_result pairs together.
    """
    if not messages:
        return []
    
    if len(messages) <= parts:
        return [[msg] for msg in messages]
    
    # Calculate tokens per part
    total_tokens = estimate_messages_tokens(messages)
    target_tokens = total_tokens // parts
    
    chunks: List[List[AgentMessage]] = []
    current_chunk: List[AgentMessage] = []
    current_tokens = 0
    pending_tool_results: List[AgentMessage] = []
    
    for i, msg in enumerate(messages):
        msg_tokens = estimate_message_tokens(msg)
        
        # Check if adding this message exceeds target
        if current_tokens + msg_tokens > target_tokens and current_chunk:
            # Save pending tool results to current chunk
            if pending_tool_results:
                current_chunk.extend(pending_tool_results)
                pending_tool_results = []
            
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0
        
        # Handle tool results - they should follow their assistant message
        if msg.role == MessageRole.TOOL_RESULT:
            pending_tool_results.append(msg)
            continue
        
        # Add message to current chunk
        current_chunk.append(msg)
        current_tokens += msg_tokens
        
        # If this is an assistant with tool calls, we need to keep
        # the pending tool results with it
        if msg.role == MessageRole.ASSISTANT and msg.tool_calls:
            # Check if we should flush pending results
            stop_reason = msg.stop_reason
            if stop_reason not in ("aborted", "error", "end_turn") and msg.tool_calls:
                # Keep pending results with this assistant
                continue
            else:
                # Tool calls completed, flush pending results to next chunk
                if pending_tool_results:
                    if not current_chunk or current_chunk[-1] != msg:
                        current_chunk.extend(pending_tool_results)
                    else:
                        chunks.append(pending_tool_results)
                    pending_tool_results = []
    
    # Flush remaining
    if current_chunk:
        current_chunk.extend(pending_tool_results)
        chunks.append(current_chunk)
    elif pending_tool_results:
        chunks.append(pending_tool_results)
    
    # Filter empty chunks
    return [c for c in chunks if c]


def repair_tool_pairing(
    messages: List[AgentMessage],
) -> tuple[List[AgentMessage], Dict[str, Any]]:
    """Repair tool_use/tool_result pairing after pruning.

    This prevents "unexpected tool_use_id" errors from the API by:
    1. Moving matching toolResult messages directly after their assistant turn
    2. Inserting synthetic error toolResults for missing IDs
    3. Dropping duplicate toolResults for the same ID
    """
    result: List[AgentMessage] = []
    seen_tool_result_ids: set = set()
    stats = {
        "dropped_duplicates": 0,
        "dropped_orphans": 0,
        "added_synthetic": 0,
    }
    
    i = 0
    while i < len(messages):
        msg = messages[i]
        
        if msg.role != MessageRole.ASSISTANT:
            # Non-assistant messages go directly to result
            result.append(msg)
            i += 1
            continue
        
        # This is an assistant message
        tool_calls = extract_tool_calls(msg)
        tool_call_ids = {tc.id for tc in tool_calls}
        
        # Add assistant message
        result.append(msg)
        
        # Collect matching tool results that follow
        j = i + 1
        pending_results: Dict[str, AgentMessage] = {}
        
        while j < len(messages) and messages[j].role == MessageRole.TOOL_RESULT:
            tr = messages[j]
            
            if tr.tool_call_id:
                if tr.tool_call_id in seen_tool_result_ids:
                    # Duplicate - drop it
                    stats["dropped_duplicates"] += 1
                elif tr.tool_call_id in tool_call_ids:
                    # Matching - keep it
                    pending_results[tr.tool_call_id] = tr
                    seen_tool_result_ids.add(tr.tool_call_id)
                else:
                    # Orphan - drop it
                    stats["dropped_orphans"] += 1
            j += 1
        
        # Add matching tool results in order
        for tc_id in tool_call_ids:
            if tc_id in pending_results:
                result.append(pending_results[tc_id])
            else:
                # Missing - add synthetic error
                synthetic = AgentMessage(
                    role=MessageRole.TOOL_RESULT,
                    content=f"Tool '{tc_id}' result not available - may have been truncated during compaction.",
                    tool_call_id=tc_id,
                    is_error=True,
                )
                result.append(synthetic)
                stats["added_synthetic"] += 1
        
        i = j
    
    return result, stats


def collect_tool_failures(messages: List[AgentMessage]) -> List[Dict[str, Any]]:
    """Collect tool failures from messages for summarization."""
    failures = []
    seen_ids = set()
    
    for msg in messages:
        if msg.role == MessageRole.TOOL_RESULT and msg.is_error:
            tc_id = msg.tool_call_id or ""
            if tc_id and tc_id not in seen_ids:
                seen_ids.add(tc_id)
                failures.append({
                    "toolCallId": tc_id,
                    "toolName": msg.tool_name or "unknown",
                    "content": msg.tool_result_content or msg.content or "",
                })
    
    return failures


def truncate_text(text: str, max_chars: int = 500) -> str:
    """Truncate text to max characters."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
