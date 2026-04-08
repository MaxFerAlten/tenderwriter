"""Agent Override Configuration.

Allows per-agent configuration overrides for model, temperature, tools, etc.
Based on oh-my-openagent's AgentOverrideConfigSchema.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ThinkingConfig(BaseModel):
    """Extended thinking configuration (Anthropic)."""

    type: Literal["enabled", "disabled"] = "disabled"
    budget_tokens: Annotated[int, Field(ge=1024, le=200000)] = 32000


class FallbackModelsConfig(BaseModel):
    """Fallback models configuration."""

    models: List[str] = Field(default_factory=list)
    on_error: Literal["fallback", "fail"] = "fallback"


class AgentPermissionConfig(BaseModel):
    """Agent permission configuration."""

    allow_bash: Optional[bool] = None
    allow_write: Optional[bool] = None
    allow_read: Optional[bool] = None
    allow_execute: Optional[bool] = None


class ToolsOverrideConfig(BaseModel):
    """Tools override configuration."""

    model_config = ConfigDict(extra="allow")


class AgentOverrideConfig(BaseModel):
    """Agent override configuration with 21 configurable fields."""

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(
        default=None,
        description="Deprecated: Use category instead. Model is inherited from category defaults.",
    )
    fallback_models: Optional[List[str]] = Field(default=None)
    variant: Optional[str] = Field(default=None)
    category: Optional[str] = Field(
        default=None,
        description="Category name to inherit model and other settings from CategoryConfig",
    )
    skills: Optional[List[str]] = Field(
        default=None,
        description="Skill names to inject into agent prompt",
    )
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.7
    top_p: Annotated[float, Field(ge=0, le=1)] = 1.0
    prompt: Optional[str] = Field(default=None)
    prompt_append: Optional[str] = Field(
        default=None,
        description="Text to append to agent prompt. Supports file:// URIs",
    )
    tools: Optional[Dict[str, bool]] = Field(default=None)
    disable: bool = False
    description: Optional[str] = Field(default=None)
    mode: Literal["subagent", "primary", "all"] = "subagent"
    color: Optional[str] = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color code",
    )
    permission: Optional[AgentPermissionConfig] = None
    max_tokens: Annotated[int, Field(ge=1)] = 4096
    thinking: Optional[ThinkingConfig] = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "medium"
    text_verbosity: Literal["low", "medium", "high"] = "medium"
    provider_options: Optional[Dict[str, Any]] = Field(default=None)
    ultrawork: Optional[Dict[str, str]] = Field(default=None)
    compaction: Optional[Dict[str, str]] = Field(default=None)


class HephaestusOverrideConfig(AgentOverrideConfig):
    """Hephaestus-specific override with additional fields."""

    allow_non_gpt_model: bool = False


AgentName = Literal[
    "sisyphus",
    "hephaestus",
    "prometheus",
    "oracle",
    "librarian",
    "explore",
    "multimodal-looker",
    "metis",
    "momus",
    "atlas",
    "sisyphus-junior",
]

BuiltinAgentName = Literal[
    "sisyphus",
    "hephaestus",
    "prometheus",
    "oracle",
    "librarian",
    "explore",
    "multimodal-looker",
    "metis",
    "momus",
    "atlas",
    "sisyphus-junior",
]

OverridableAgentName = Literal[
    "build",
    "plan",
    "sisyphus",
    "hephaestus",
    "sisyphus-junior",
    "prometheus",
    "metis",
    "momus",
    "oracle",
    "librarian",
    "explore",
    "multimodal-looker",
    "atlas",
]


class AgentOverridesConfig(BaseModel):
    """Container for all agent override configurations."""

    model_config = ConfigDict(extra="allow")

    build: Optional[AgentOverrideConfig] = None
    plan: Optional[AgentOverrideConfig] = None
    sisyphus: Optional[AgentOverrideConfig] = None
    hephaestus: Optional[HephaestusOverrideConfig] = None
    sisyphus_junior: Optional[AgentOverrideConfig] = Field(default=None, alias="sisyphus-junior")
    prometheus: Optional[AgentOverrideConfig] = None
    metis: Optional[AgentOverrideConfig] = None
    momus: Optional[AgentOverrideConfig] = None
    oracle: Optional[AgentOverrideConfig] = None
    librarian: Optional[AgentOverrideConfig] = None
    explore: Optional[AgentOverrideConfig] = None
    multimodal_looker: Optional[AgentOverrideConfig] = Field(default=None, alias="multimodal-looker")
    atlas: Optional[AgentOverrideConfig] = None

    def get_agent_config(self, agent_name: str) -> Optional[AgentOverrideConfig]:
        """Get configuration for a specific agent."""
        name_mapping = {
            "build": self.build,
            "plan": self.plan,
            "sisyphus": self.sisyphus,
            "hephaestus": self.hephaestus,
            "sisyphus-junior": self.sisyphus_junior,
            "prometheus": self.prometheus,
            "metis": self.metis,
            "momus": self.momus,
            "oracle": self.oracle,
            "librarian": self.librarian,
            "explore": self.explore,
            "multimodal-looker": self.multimodal_looker,
            "atlas": self.atlas,
        }
        return name_mapping.get(agent_name)

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump model with proper key naming."""
        data = super().model_dump(**kwargs)
        if "sisyphus_junior" in data and data["sisyphus_junior"] is not None:
            data["sisyphus-junior"] = data.pop("sisyphus_junior")
        if "multimodal_looker" in data and data["multimodal_looker"] is not None:
            data["multimodal-looker"] = data.pop("multimodal_looker")
        return data
