"""Agent schemas — agent definitions and configuration."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AgentMode(str, Enum):
    """Whether the agent uses the user-selected model or its own."""

    PRIMARY = "primary"      # Uses user-selected model
    SUBAGENT = "subagent"    # Uses its own model, ignores UI selection


class AgentCategory(str, Enum):
    """Agent specialization category."""

    ORCHESTRATION = "orchestration"
    EXPLORATION = "exploration"
    ADVISOR = "advisor"
    SPECIALIST = "specialist"
    UTILITY = "utility"


class AgentCost(str, Enum):
    """Relative cost level for token budgeting."""

    FREE = "free"
    CHEAP = "cheap"
    EXPENSIVE = "expensive"


class AgentDefinition(BaseModel):
    """Full definition of an agent."""

    name: str
    description: str
    mode: AgentMode = AgentMode.SUBAGENT
    default_model: str = "claude-sonnet-4-20250514"
    category: AgentCategory = AgentCategory.UTILITY
    cost: AgentCost = AgentCost.CHEAP
    system_prompt: str = ""
    max_tokens: int = 16384
    tools: list[str] = []    # Tool names this agent can use (empty = all)
    enabled: bool = True
