"""Mode state management for active workflows."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

@dataclass
class ModeState:
    mode: Literal["idle", "ralph", "team", "analyze", "plan", "tdd", "cancel"] = "idle"
    active: bool = False
    started_at: str = ""
    metadata: dict = field(default_factory=dict)


class ModeManager:
    _current_mode: ModeState = field(default_factory=ModeState, init=False)
    
    @classmethod
    def get_current(cls) -> ModeState:
        return cls._current_mode
    
    @classmethod
    def set_mode(cls, mode: str, metadata: dict = None):
        cls._current_mode = ModeState(
            mode=mode,
            active=True,
            started_at=datetime.utcnow().isoformat(),
            metadata=metadata or {}
        )
    
    @classmethod
    def clear_mode(cls):
        cls._current_mode = ModeState()

    @classmethod
    def cancel_mode(cls, mode: str) -> dict:
        """Cancel a specific mode."""
        if cls._current_mode.mode != mode:
            return {"status": "not_active", "mode": cls._current_mode.mode}
        
        result = {
            "cancelled": mode,
            "preserved": [],
        }
        cls.clear_mode()
        return result