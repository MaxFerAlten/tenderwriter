"""WebSocket message schemas — the real-time protocol between frontend and backend.

All messages use a discriminated union on the `type` field.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.messages import TokenUsage


# =============================================================================
# Client -> Server (upstream)
# =============================================================================


class WSAttachment(BaseModel):
    """An attachment (image, file) sent with a message."""

    type: str  # e.g., "image/png", "text/plain"
    url: str | None = None  # URL or base64 data
    name: str | None = None


class WSUserMessage(BaseModel):
    """User sends a chat message."""

    type: Literal["user_message"] = "user_message"
    content: str
    message_id: str = ""
    attachments: list[WSAttachment] = Field(default_factory=list)


class WSToolPermissionResponse(BaseModel):
    """User approves or denies a tool execution."""

    type: Literal["tool_permission_response"] = "tool_permission_response"
    tool_use_id: str
    decision: Literal["approve", "deny"]
    reason: str | None = None


class WSAbort(BaseModel):
    """User aborts the current operation."""

    type: Literal["abort"] = "abort"
    reason: str = "user_cancelled"


class WSSessionConfig(BaseModel):
    """User updates session configuration mid-flight."""

    type: Literal["session_config"] = "session_config"
    model: str | None = None
    permission_mode: str | None = None


WSClientMessage = WSUserMessage | WSToolPermissionResponse | WSAbort | WSSessionConfig


# =============================================================================
# Server -> Client (downstream)
# =============================================================================


class WSAssistantText(BaseModel):
    """Streaming text delta from the assistant."""

    type: Literal["assistant_text"] = "assistant_text"
    delta: str
    message_id: str


class WSAssistantThinking(BaseModel):
    """Streaming thinking delta from the assistant."""

    type: Literal["assistant_thinking"] = "assistant_thinking"
    delta: str
    message_id: str


class WSMessageStart(BaseModel):
    """A new assistant message has begun."""

    type: Literal["assistant_message_start"] = "assistant_message_start"
    message_id: str


class WSMessageEnd(BaseModel):
    """An assistant message is complete."""

    type: Literal["assistant_message_end"] = "assistant_message_end"
    message_id: str


class WSToolUseStart(BaseModel):
    """A tool invocation is beginning."""

    type: Literal["tool_use_start"] = "tool_use_start"
    tool_use_id: str
    tool_name: str
    message_id: str


class WSToolResult(BaseModel):
    """A tool has produced a result."""

    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    tool_name: str
    content: str
    is_error: bool = False


class WSToolProgress(BaseModel):
    """Incremental progress from a running tool (e.g., bash stdout)."""

    type: Literal["tool_progress"] = "tool_progress"
    tool_use_id: str
    data: str


class WSPermissionRequest(BaseModel):
    """Server asks the user to approve a tool execution."""

    type: Literal["permission_request"] = "permission_request"
    tool_use_id: str
    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "medium"


class WSError(BaseModel):
    """An error occurred."""

    type: Literal["error"] = "error"
    error: str
    code: str = "internal_error"


class WSTurnStart(BaseModel):
    """An agent turn has begun."""

    type: Literal["turn_start"] = "turn_start"
    turn_number: int = 0
    agent_name: str = "sisyphus"


class WSTurnEnd(BaseModel):
    """An agent turn is complete."""

    type: Literal["turn_end"] = "turn_end"
    stop_reason: str = "end_turn"
    usage: TokenUsage = Field(default_factory=TokenUsage)


class WSCostUpdate(BaseModel):
    """Updated cost information."""

    type: Literal["cost_update"] = "cost_update"
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0


class WSAgentSwitch(BaseModel):
    """Agent identity has changed (e.g. delegation)."""

    type: Literal["agent_switch"] = "agent_switch"
    agent_name: str
    task: str | None = None

class WSUIUpdate(BaseModel):
    """Agent updates the UI canvas (A2UI)."""

    type: Literal["ui_update"] = "ui_update"
    artifact_id: str
    title: str
    content: str
    language: str | None = None


WSServerMessage = (
    WSAssistantText
    | WSAssistantThinking
    | WSMessageStart
    | WSMessageEnd
    | WSToolUseStart
    | WSToolResult
    | WSToolProgress
    | WSPermissionRequest
    | WSError
    | WSTurnStart
    | WSTurnEnd
    | WSCostUpdate
    | WSAgentSwitch
    | WSUIUpdate
)
