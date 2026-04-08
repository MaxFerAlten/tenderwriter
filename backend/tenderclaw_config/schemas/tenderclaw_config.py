"""Root TenderClaw Configuration Schema.

Based on oh-my-openagent's OhMyOpenCodeConfigSchema.
Brings together all configuration sections.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from backend.tenderclaw_config.schemas.agent_overrides import AgentOverridesConfig
from backend.tenderclaw_config.schemas.background_task import BackgroundTaskConfig
from backend.tenderclaw_config.schemas.categories import CategoriesConfig
from backend.tenderclaw_config.schemas.comment_checker import CommentCheckerConfig
from backend.tenderclaw_config.schemas.experimental import ExperimentalConfig
from backend.tenderclaw_config.schemas.git_master import GitMasterConfig
from backend.tenderclaw_config.schemas.hooks import HookConfig, HooksConfig
from backend.tenderclaw_config.schemas.ralph_loop import RalphLoopConfig
from backend.tenderclaw_config.schemas.sisyphus import SisyphusConfig
from backend.tenderclaw_config.schemas.skills import SkillsConfig


class RuntimeFallbackConfig(BaseModel):
    """Runtime fallback configuration for model switching on errors."""

    enabled: bool = False
    retry_on_errors: List[int] = [400, 429]
    timeout_seconds: int = 30


class TmuxLayout(BaseModel):
    """Tmux window layout configuration."""

    window_name: str = "tenderclaw"
    panes: Optional[Dict[str, str]] = None


class TmuxConfig(BaseModel):
    """Tmux session configuration."""

    enabled: bool = False
    layout: Optional[TmuxLayout] = None


class WebsearchConfig(BaseModel):
    """Web search provider configuration."""

    provider: str = "exa"
    api_key: Optional[str] = None


class NotificationConfig(BaseModel):
    """OS notification configuration."""

    enabled: bool = True
    sound: bool = True


class ModelCapabilitiesConfig(BaseModel):
    """Model capabilities configuration."""

    enabled: bool = False
    auto_refresh_on_start: bool = True
    refresh_timeout_ms: int = 5000
    source_url: str = "https://models.dev/api.json"


class BrowserAutomationConfig(BaseModel):
    """Browser automation configuration."""

    provider: str = "playwright"


class ClaudeCodeConfig(BaseModel):
    """Claude Code compatibility settings."""

    enabled: bool = False
    config_path: Optional[str] = None


class StartWorkConfig(BaseModel):
    """Start work command configuration."""

    auto_commit: bool = False


class BabysittingConfig(BaseModel):
    """Unstable agent babysitting configuration."""

    enabled: bool = False
    check_interval_ms: int = 60000


class TenderClawConfig(BaseModel):
    """Root configuration schema for TenderClaw.

    Supports all configuration options from oh-my-openagent
    with hierarchical precedence: defaults < config file < env < runtime.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema: Optional[str] = Field(default=None, alias="$schema")

    new_task_system_enabled: bool = False
    default_run_agent: Optional[str] = None

    disabled_mcps: Optional[List[str]] = None
    disabled_agents: Optional[List[str]] = None
    disabled_skills: Optional[List[str]] = None
    disabled_hooks: Optional[List[str]] = None
    disabled_commands: Optional[List[str]] = None
    disabled_tools: Optional[List[str]] = None

    hashline_edit: bool = False
    model_fallback: bool = False

    agents: Optional[AgentOverridesConfig] = None
    categories: Optional[CategoriesConfig] = None
    claude_code: Optional[ClaudeCodeConfig] = None
    comment_checker: Optional[CommentCheckerConfig] = None
    experimental: Optional[ExperimentalConfig] = None
    auto_update: bool = True
    skills: Optional[SkillsConfig] = None
    ralph_loop: Optional[RalphLoopConfig] = None
    runtime_fallback: Union[bool, RuntimeFallbackConfig] = False
    background_task: Optional[BackgroundTaskConfig] = None
    notification: Optional[NotificationConfig] = None
    model_capabilities: Optional[ModelCapabilitiesConfig] = None
    babysitting: Optional[BabysittingConfig] = None
    git_master: Optional[GitMasterConfig] = Field(
        default_factory=lambda: GitMasterConfig(
            commit_footer=True,
            include_co_authored_by=True,
            git_env_prefix="GIT_MASTER=1",
        )
    )
    browser_automation_engine: Optional[BrowserAutomationConfig] = None
    websearch: Optional[WebsearchConfig] = None
    tmux: Optional[TmuxConfig] = None
    sisyphus: Optional[SisyphusConfig] = None
    start_work: Optional[StartWorkConfig] = None
    hooks: Optional[HooksConfig] = None

    migrations: Optional[List[str]] = Field(
        default=None,
        description="Migration history to prevent re-applying migrations",
        alias="_migrations",
    )

    def is_agent_disabled(self, agent_name: str) -> bool:
        """Check if an agent is disabled."""
        if not self.disabled_agents:
            return False
        return agent_name in self.disabled_agents

    def is_hook_disabled(self, hook_name: str) -> bool:
        """Check if a hook is disabled."""
        if not self.disabled_hooks:
            return False
        return hook_name in self.disabled_hooks

    def is_mcp_disabled(self, mcp_name: str) -> bool:
        """Check if an MCP is disabled."""
        if not self.disabled_mcps:
            return False
        return mcp_name in self.disabled_mcps

    def is_skill_disabled(self, skill_name: str) -> bool:
        """Check if a skill is disabled."""
        if not self.disabled_skills:
            return False
        return skill_name in self.disabled_skills

    def is_tool_disabled(self, tool_name: str) -> bool:
        """Check if a tool is disabled."""
        if not self.disabled_tools:
            return False
        return tool_name in self.disabled_tools

    def get_agent_config(self, agent_name: str):
        """Get configuration for a specific agent."""
        if self.agents:
            return self.agents.get_agent_config(agent_name)
        return None

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump model to dictionary, excluding None values by default."""
        exclude_none = kwargs.pop("exclude_none", True)
        data = super().model_dump(exclude_none=exclude_none, **kwargs)
        if "schema" in data and data["schema"] is not None:
            data["$schema"] = data.pop("schema")
        if "migrations" in data and data["migrations"] is not None:
            data["_migrations"] = data.pop("migrations")
        return data
