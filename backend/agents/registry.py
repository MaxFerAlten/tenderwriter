"""Agent registry — register and look up specialized agents.

Simple dict-based registry for agent definitions.
Acts as the source of truth for all available agent roles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.schemas.agents import AgentCategory, AgentCost, AgentDefinition, AgentMode

PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


class AgentRegistry:
    """Registry of all available specialized agents."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, agent: AgentDefinition) -> None:
        """Register an agent definition."""
        self._agents[agent.name.lower()] = agent

    def get(self, name: str) -> AgentDefinition:
        """Get an agent by name."""
        agent = self._agents.get(name.lower())
        if not agent:
            raise ValueError(f"Unknown agent: {name}")
        return agent

    def list_agents(self) -> list[AgentDefinition]:
        """List all registered agents."""
        return list(self._agents.values())

    def list_all(self) -> list[AgentDefinition]:
        """List all agents."""
        return list(self._agents.values())


def _load_prompt(filename: str) -> str:
    """Read a system prompt from the prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        return f"Role: {filename.replace('.md', '').capitalize()}"
    return path.read_text("utf-8")


def register_builtin_agents(registry: AgentRegistry) -> None:
    """Register the 12 core agents of TenderClaw."""
    agents = [
        AgentDefinition(
            name="sisyphus",
            description="Primary orchestrator and executor. The 'executor' role.",
            mode=AgentMode.PRIMARY,
            category=AgentCategory.ORCHESTRATION,
            cost=AgentCost.CHEAP,
            system_prompt=_load_prompt("executor.md"),
            tools=[], # Can use all tools
        ),
        AgentDefinition(
            name="oracle",
            description="Deep research and architectural planning specialist.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.EXPLORATION,
            cost=AgentCost.EXPENSIVE,
            system_prompt=_load_prompt("architect.md"),
            default_model="claude-sonnet-4-20250514",
        ),
        AgentDefinition(
            name="explorer",
            description="Structural search expert using AST-grep and LSP tools.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.EXPLORATION,
            system_prompt="You are **Explorer**, specialized in structural code search and understanding.",
            tools=["AstGrep", "LspGotoDefinition", "LspFindReferences", "Grep", "Glob"],
        ),
        AgentDefinition(
            name="metis",
            description="Strategy and planning specialist. Creates detailed implementation guides.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.ADVISOR,
            system_prompt=_load_prompt("strategy.md"),
        ),
        AgentDefinition(
            name="momus",
            description="Code review, audit and critique specialist. Verification of tasks.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.ADVISOR,
            system_prompt=_load_prompt("reviewer.md"),
        ),
        AgentDefinition(
            name="sentinel",
            description="Security audit specialized agent.",
            category=AgentCategory.SPECIALIST,
            system_prompt="You are **Sentinel**, an expert in security auditing and penetration testing.",
        ),
        AgentDefinition(
            name="hephaestus",
            description="GPT-native deep worker for complex implementation tasks.",
            mode=AgentMode.PRIMARY,
            category=AgentCategory.ORCHESTRATION,
            cost=AgentCost.EXPENSIVE,
            default_model="gpt-4o",
            system_prompt=_load_prompt("hephaestus.md"),
        ),
        AgentDefinition(
            name="atlas",
            description="Gemini-powered conductor and multi-agent coordinator.",
            mode=AgentMode.PRIMARY,
            category=AgentCategory.ORCHESTRATION,
            cost=AgentCost.EXPENSIVE,
            default_model="gemini-2.5-pro",
            system_prompt=_load_prompt("conductor.md"),
        ),
        AgentDefinition(
            name="librarian",
            description="Documentation, SDK, and framework knowledge specialist.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.EXPLORATION,
            system_prompt=_load_prompt("librarian.md"),
            tools=["WebSearch", "Read", "Grep", "Glob"],
        ),
        AgentDefinition(
            name="scribe",
            description="Documentation writer and technical writer.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.UTILITY,
            system_prompt=_load_prompt("scribe.md"),
            tools=["Read", "Write", "Edit", "Glob"],
        ),
        AgentDefinition(
            name="fixer",
            description="Bug fix specialist — diagnose and repair with minimal diff.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.SPECIALIST,
            default_model="claude-sonnet-4-20250514",
            system_prompt=_load_prompt("debugger.md"),
        ),
        AgentDefinition(
            name="looker",
            description="Screenshot and visual analysis specialist.",
            mode=AgentMode.SUBAGENT,
            category=AgentCategory.SPECIALIST,
            default_model="claude-sonnet-4-20250514",
            system_prompt=_load_prompt("looker.md"),
        ),
    ]

    for agent in agents:
        registry.register(agent)


# Module-level instance
agent_registry = AgentRegistry()
register_builtin_agents(agent_registry)
