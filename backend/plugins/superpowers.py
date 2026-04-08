"""Superpowers Plugin — integrates the external superpowers library.

This plugin bridges TenderClaw with Jesse Vincent's 'superpowers'
multi-agent workflow and skills.

On startup it:
1. Loads agent definitions from superpowers/agents/*.md
2. Registers them in the AgentRegistry as SPECIALIST subagents
3. Loads command definitions from superpowers/commands/*.md
4. Registers each as a SuperpowerCommandTool in the ToolRegistry
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from backend.plugins.base import BasePlugin
from backend.tools.registry import ToolRegistry
from backend.agents.registry import AgentRegistry

logger = logging.getLogger("tenderclaw.plugins.superpowers")

SUPERPOWERS_PATH = Path(r"d:\MY_AI\claude-code\superpowers")


class SuperpowersPlugin(BasePlugin):
    """Integrates Jesse's Superpowers skill library and workflow-driven development."""

    @property
    def name(self) -> str:
        return "superpowers"

    @property
    def version(self) -> str:
        return "2.1.0"

    def on_init(self, config: dict[str, Any]) -> None:
        """Verify the path exists and log metadata."""
        if not SUPERPOWERS_PATH.exists():
            raise FileNotFoundError(f"Superpowers not found at {SUPERPOWERS_PATH}")
        logger.info("Superpowers plugin init — path: %s", SUPERPOWERS_PATH)

    def on_register_skills(self, skills_path: str) -> None:
        """Register the skills directory from superpowers."""
        # TenderClaw's skills system reads CLAUDE.md / SKILL.md from the skills dir.
        # We surface the superpowers skills path here for the core.skills module.
        try:
            from backend.core import skills as skills_module
            sp_skills = SUPERPOWERS_PATH / "skills"
            if sp_skills.exists():
                skills_module.add_skills_path(str(sp_skills))
                logger.info("Registered superpowers skills path: %s", sp_skills)
        except Exception as exc:
            logger.warning("Could not register superpowers skills: %s", exc)

    def on_register_agents(self, registry: AgentRegistry) -> None:
        """Load and register agents from superpowers/agents/*.md."""
        from backend.plugins.superpowers_loader import load_agents_from_markdown
        from backend.schemas.agents import AgentCategory, AgentCost, AgentDefinition, AgentMode

        agents_dir = SUPERPOWERS_PATH / "agents"
        descriptors = load_agents_from_markdown(agents_dir)

        for desc in descriptors:
            # Prefix name to avoid collision with built-ins
            agent_name = f"sp_{desc['name']}"
            agent = AgentDefinition(
                name=agent_name,
                description=f"[Superpowers] {desc['description']}",
                mode=AgentMode.SUBAGENT,
                category=AgentCategory.SPECIALIST,
                cost=AgentCost.CHEAP,
                default_model=desc.get("model", "claude-sonnet-4-20250514"),
                system_prompt=desc["system_prompt"],
                tools=[],
            )
            registry.register(agent)
            logger.info("Registered superpowers agent: %s", agent_name)

        if descriptors:
            logger.info("Registered %d superpowers agents", len(descriptors))

    def on_register_tools(self, registry: ToolRegistry) -> None:
        """Load and register commands from superpowers/commands/*.md."""
        from backend.plugins.superpowers_loader import load_commands_from_markdown
        from backend.tools.superpowers_tool import SuperpowerCommandTool

        commands_dir = SUPERPOWERS_PATH / "commands"
        descriptors = load_commands_from_markdown(commands_dir)

        for desc in descriptors:
            tool = SuperpowerCommandTool(
                name=desc["name"],
                description=desc["description"],
                body=desc["body"],
            )
            registry.register(tool)
            logger.info("Registered superpowers tool: %s", desc["name"])

        if descriptors:
            logger.info("Registered %d superpowers command tools", len(descriptors))
