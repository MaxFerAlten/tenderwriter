"""Message schemas — the core data model for conversations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Message author role."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ContentBlockType(str, Enum):
    """Discriminator for content blocks inside a message."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    IMAGE = "image"


class TextBlock(BaseModel):
    """Plain text content block."""

    type: ContentBlockType = ContentBlockType.TEXT
    text: str


class ThinkingBlock(BaseModel):
    """Extended thinking content block."""

    type: ContentBlockType = ContentBlockType.THINKING
    thinking: str


class ToolUseBlock(BaseModel):
    """Tool invocation content block."""

    type: ContentBlockType = ContentBlockType.TOOL_USE
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    """Tool execution result content block."""

    type: ContentBlockType = ContentBlockType.TOOL_RESULT
    tool_use_id: str
    content: str
    is_error: bool = False


ContentBlock = TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock


class Message(BaseModel):
    """A single conversation message."""

    role: Role
    content: list[ContentBlock] | str
    message_id: str = ""


class TokenUsage(BaseModel):
    """Token usage for a single API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens
