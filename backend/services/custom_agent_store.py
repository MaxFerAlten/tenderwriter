"""Custom Agent Store — persist user-created and user-edited agents to disk.

Agents are stored as individual JSON files in .tenderclaw/agents/.
Built-in agents from register_builtin_agents() are NOT stored here;
this store exclusively manages user-defined overrides and additions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.schemas.agents import AgentDefinition

logger = logging.getLogger("tenderclaw.services.custom_agent_store")


class CustomAgentStore:
    """File-backed store for user-managed agents."""

    def __init__(self, storage_path: str = ".tenderclaw/agents") -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def load_all(self) -> list[AgentDefinition]:
        """Load all custom agents from disk."""
        agents: list[AgentDefinition] = []
        for file_path in sorted(self.storage_path.glob("*.json")):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                agents.append(AgentDefinition.model_validate(data))
            except Exception as exc:
                logger.error("Failed to load custom agent %s: %s", file_path.name, exc)
        return agents

    def save(self, agent: AgentDefinition) -> None:
        """Persist an agent definition to disk."""
        file_path = self.storage_path / f"{agent.name}.json"
        file_path.write_text(agent.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Custom agent saved: %s", agent.name)

    def delete(self, name: str) -> bool:
        """Delete a custom agent from disk. Returns True if deleted."""
        file_path = self.storage_path / f"{name}.json"
        if file_path.exists():
            file_path.unlink()
            logger.info("Custom agent deleted: %s", name)
            return True
        return False

    def exists(self, name: str) -> bool:
        """Check if a custom agent file exists."""
        return (self.storage_path / f"{name}.json").exists()


# Module-level singleton
custom_agent_store = CustomAgentStore()
