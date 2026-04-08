"""Ralph autonomous execution state management."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
from typing import Literal


@dataclass
class RalphState:
    active: bool = False
    iteration: int = 0
    max_iterations: int = 10
    current_phase: Literal["intake", "executing", "verifying", "fixing", "complete"] = "intake"
    started_at: str = ""
    task_slug: str = ""
    context_snapshot_path: str = ""
    changed_files: list[str] = field(default_factory=list)


class RalphStateManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir / "ralph"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: RalphState):
        path = self.state_dir / f"{state.task_slug}.json"
        with open(path, "w") as f:
            json.dump({
                "active": state.active,
                "iteration": state.iteration,
                "max_iterations": state.max_iterations,
                "current_phase": state.current_phase,
                "started_at": state.started_at,
                "task_slug": state.task_slug,
                "context_snapshot_path": state.context_snapshot_path,
                "changed_files": state.changed_files,
            }, f, indent=2)

    def load(self, task_slug: str) -> RalphState | None:
        path = self.state_dir / f"{task_slug}.json"
        if not path.exists():
            return None
        with open(path) as f:
            data = json.load(f)
            return RalphState(**data)

    def start(self, task_slug: str, context_path: str = "") -> RalphState:
        state = RalphState(
            active=True,
            iteration=1,
            started_at=datetime.utcnow().isoformat(),
            task_slug=task_slug,
            context_snapshot_path=context_path,
        )
        self.save(state)
        return state

    def increment_iteration(self, state: RalphState) -> RalphState:
        state.iteration += 1
        state.current_phase = "executing"
        self.save(state)
        return state

    def set_phase(self, state: RalphState, phase: str) -> RalphState:
        state.current_phase = phase  # type: ignore
        self.save(state)
        return state

    def complete(self, state: RalphState):
        state.active = False
        state.current_phase = "complete"
        self.save(state)