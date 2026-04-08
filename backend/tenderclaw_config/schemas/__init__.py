"""Configuration schemas for TenderClaw.

Based on oh-my-openagent's Zod schema system, ported to Pydantic for Python.
"""

from backend.tenderclaw_config.schemas.agent_overrides import (
    AgentOverrideConfig,
    AgentOverridesConfig,
    HephaestusOverrideConfig,
)
from backend.tenderclaw_config.schemas.background_task import (
    BackgroundTaskConfig,
    CircuitBreakerConfig,
)
from backend.tenderclaw_config.schemas.categories import (
    BUILTIN_CATEGORIES,
    BuiltinCategoryName,
    CategoriesConfig,
    CategoryConfig,
)
from backend.tenderclaw_config.schemas.comment_checker import CommentCheckerConfig
from backend.tenderclaw_config.schemas.experimental import (
    DynamicContextPruningConfig,
    ExperimentalConfig,
)
from backend.tenderclaw_config.schemas.git_master import GitMasterConfig
from backend.tenderclaw_config.schemas.hooks import HookConfig, HookName, HooksConfig
from backend.tenderclaw_config.schemas.ralph_loop import RalphLoopConfig
from backend.tenderclaw_config.schemas.sisyphus import SisyphusConfig, SisyphusTasksConfig
from backend.tenderclaw_config.schemas.skills import (
    BuiltinSkillName,
    SkillDefinition,
    SkillsConfig,
    SkillsSourcesConfig,
)
from backend.tenderclaw_config.schemas.tenderclaw_config import (
    BabysittingConfig,
    BrowserAutomationConfig,
    ClaudeCodeConfig,
    ModelCapabilitiesConfig,
    NotificationConfig,
    RuntimeFallbackConfig,
    StartWorkConfig,
    TenderClawConfig,
    TmuxConfig,
    WebsearchConfig,
)

__all__ = [
    "AgentOverrideConfig",
    "AgentOverridesConfig",
    "BabysittingConfig",
    "BackgroundTaskConfig",
    "BUILTIN_CATEGORIES",
    "BrowserAutomationConfig",
    "BuiltinCategoryName",
    "BuiltinSkillName",
    "CategoriesConfig",
    "CategoryConfig",
    "CircuitBreakerConfig",
    "ClaudeCodeConfig",
    "CommentCheckerConfig",
    "DynamicContextPruningConfig",
    "ExperimentalConfig",
    "GitMasterConfig",
    "HephaestusOverrideConfig",
    "HookConfig",
    "HookName",
    "HooksConfig",
    "ModelCapabilitiesConfig",
    "NotificationConfig",
    "RalphLoopConfig",
    "RuntimeFallbackConfig",
    "SisyphusConfig",
    "SisyphusTasksConfig",
    "SkillDefinition",
    "SkillsConfig",
    "SkillsSourcesConfig",
    "StartWorkConfig",
    "TenderClawConfig",
    "TmuxConfig",
    "WebsearchConfig",
]
