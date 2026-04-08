"""Session State Management — persistent session lifecycle with recovery.

Manages session persistence, resume, cost tracking, usage metrics, and
conversation history with disk-based checkpointing.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.schemas.sessions import SessionStatus
from backend.config import settings
from backend.utils.errors import SessionNotFoundError

logger = logging.getLogger("tenderclaw.runtime.session_state")

# Session persistence directory
SESSION_STATE_DIR = Path(".tenderclaw/sessions")
SESSION_STATE_DIR.mkdir(parents=True, exist_ok=True)

# Session timeout (24 hours)
SESSION_TIMEOUT_HOURS = 24


@dataclass
class UsageMetrics:
    """Token usage and cost tracking."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: float = 0.0

    def add_usage(self, input_tokens: int, output_tokens: int, cost_per_1k_input: float, cost_per_1k_output: float) -> None:
        """Add token usage and calculate cost."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        input_cost = (input_tokens / 1000) * cost_per_1k_input
        output_cost = (output_tokens / 1000) * cost_per_1k_output
        self.total_cost_usd += input_cost + output_cost

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class SessionState:
    """Persistent session state with full lifecycle management."""
    session_id: str
    status: SessionStatus = SessionStatus.IDLE
    model: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    working_directory: str = "."
    messages: List[Dict[str, Any]] = field(default_factory=list)
    usage: UsageMetrics = field(default_factory=UsageMetrics)
    system_prompt_append: str = ""
    model_config: Dict[str, Any] = field(default_factory=dict)
    api_keys: Dict[str, str] = field(default_factory=dict)
    should_abort: bool = False
    is_expired: bool = False
    checkpoint_count: int = 0

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def is_expired_session(self) -> bool:
        """Check if session has expired based on timeout."""
        if self.is_expired:
            return True
        
        expiry_time = self.last_activity + timedelta(hours=SESSION_TIMEOUT_HOURS)
        return datetime.utcnow() > expiry_time

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['created_at'] = self.created_at.isoformat()
        data['updated_at'] = self.updated_at.isoformat()
        data['last_activity'] = self.last_activity.isoformat()
        data['usage'] = self.usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionState':
        """Create SessionState from dictionary."""
        # Convert ISO format strings back to datetime objects
        if 'created_at' in data and isinstance(data['created_at'], str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'updated_at' in data and isinstance(data['updated_at'], str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if 'last_activity' in data and isinstance(data['last_activity'], str):
            data['last_activity'] = datetime.fromisoformat(data['last_activity'])
        
        # Handle usage metrics
        if 'usage' in data and isinstance(data['usage'], dict):
            usage_data = data['usage']
            data['usage'] = UsageMetrics(
                input_tokens=usage_data.get('input_tokens', 0),
                output_tokens=usage_data.get('output_tokens', 0),
                total_cost_usd=usage_data.get('total_cost_usd', 0.0)
            )
        
        return cls(**data)

    def save_to_disk(self) -> None:
        """Save session state to disk."""
        self.checkpoint_count += 1
        self.touch()
        
        file_path = SESSION_STATE_DIR / f"{self.session_id}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug("Session %s saved to disk (checkpoint %d)", self.session_id, self.checkpoint_count)
        except Exception as e:
            logger.error("Failed to save session %s to disk: %s", self.session_id, e)
            raise

    @classmethod
    def load_from_disk(cls, session_id: str) -> 'SessionState':
        """Load session state from disk."""
        file_path = SESSION_STATE_DIR / f"{session_id}.json"
        if not file_path.exists():
            raise SessionNotFoundError(f"Session not found: {session_id}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            session = cls.from_dict(data)
            logger.debug("Session %s loaded from disk", session_id)
            return session
        except Exception as e:
            logger.error("Failed to load session %s from disk: %s", session_id, e)
            raise SessionNotFoundError(f"Failed to load session: {e}")

    @classmethod
    def list_sessions(cls) -> List[str]:
        """List all persisted session IDs."""
        if not SESSION_STATE_DIR.exists():
            return []
        
        session_files = SESSION_STATE_DIR.glob("*.json")
        return [f.stem for f in session_files if f.is_file()]

    @classmethod
    def delete_from_disk(cls, session_id: str) -> None:
        """Delete session state from disk."""
        file_path = SESSION_STATE_DIR / f"{session_id}.json"
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug("Session %s deleted from disk", session_id)
        except Exception as e:
            logger.error("Failed to delete session %s from disk: %s", session_id, e)
            raise

    @classmethod
    def cleanup_expired_sessions(cls) -> int:
        """Clean up expired sessions from disk. Returns count of removed sessions."""
        removed_count = 0
        for session_id in cls.list_sessions():
            try:
                session = cls.load_from_disk(session_id)
                if session.is_expired_session():
                    cls.delete_from_disk(session_id)
                    removed_count += 1
                    logger.info("Removed expired session: %s", session_id)
            except SessionNotFoundError:
                # Session was already deleted
                pass
            except Exception as e:
                logger.error("Error checking session %s for expiry: %s", session_id, e)
        
        return removed_count