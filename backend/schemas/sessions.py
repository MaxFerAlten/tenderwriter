"""Session schemas — session lifecycle and state."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from backend.schemas.messages import Message, TokenUsage


class SessionStatus(str, Enum):
    """Session lifecycle state."""

    ACTIVE = "active"
    IDLE = "idle"
    BUSY = "busy"
    CLOSED = "closed"


class SessionCreate(BaseModel):
    """Request body to create a new session."""

    model: str | None = None
    system_prompt_append: str | None = None
    working_directory: str | None = None


class SessionInfo(BaseModel):
    """Public session metadata returned by the API."""

    session_id: str
    status: SessionStatus = SessionStatus.IDLE
    model: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_cost_usd: float = 0.0


class SessionState(BaseModel):
    """Full internal session state (includes message history)."""

    session_id: str
    status: SessionStatus = SessionStatus.IDLE
    model: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: list[Message] = Field(default_factory=list)
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_cost_usd: float = 0.0
    working_directory: str = ""
    system_prompt_append: str = ""
    should_abort: bool = False

    def to_info(self) -> SessionInfo:
        """Convert to public-facing SessionInfo."""
        return SessionInfo(
            session_id=self.session_id,
            status=self.status,
            model=self.model,
            created_at=self.created_at,
            message_count=len(self.messages),
            total_usage=self.total_usage,
            total_cost_usd=self.total_cost_usd,
        )
