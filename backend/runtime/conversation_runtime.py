"""Conversation runtime core (Wave 1) - lightweight orchestration.

This module provides a minimal surface to manage per-session
conversation runtime state, leveraging existing components for prompt
generation and message history. It is intentionally small and extensible
to support future Wave 1 features like persistence, resume and hooks.
"""

from __future__ import annotations

from typing import Any, List
from datetime import datetime

from backend.core.system_prompt import build_system_prompt
from backend.schemas.messages import Message, Role
from backend.schemas.sessions import SessionStatus
from backend.services.session_store import session_store


class ConversationRuntime:
    """Lightweight per-session runtime wrapper."""

    def __init__(self, session_id: str):
        self.session = session_store.get(session_id)

    def append_user_message(self, text: str) -> None:
        self.session.messages.append(Message(role=Role.USER, content=text, message_id=f"msg_{datetime.utcnow().timestamp()}") )

    def append_assistant_message(self, text: str) -> None:
        self.session.messages.append(Message(role=Role.ASSISTANT, content=text, message_id=f"msg_{datetime.utcnow().timestamp()}") )

    def current_prompt(self) -> str:
        """Return the current system prompt combined with messages."""
        system = build_system_prompt(working_directory=self.session.working_directory,
                                     append=self.session.system_prompt_append)
        # This is a minimal representation; in a real runtime we would assemble the messages
        messages = "\n".join([m.content for m in self.session.messages if isinstance(m.content, str)])
        return f"{system}\n{messages}"

    def persist(self) -> None:
        """Persist current session state to storage."""
        session_store.get(self.session.session_id).checkpoint_count += 0  # no-op hook to ensure session exists
        # Use existing session_store to save if implemented; placeholder for Wave 1
        return None
