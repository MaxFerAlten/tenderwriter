"""Experimental Feature Flags Configuration.

Based on oh-my-openagent's ExperimentalConfigSchema.
"""

from __future__ import annotations

from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TurnProtectionConfig(BaseModel):
    """Turn protection configuration."""

    enabled: bool = True
    turns: Annotated[int, Field(ge=1, le=10)] = 3


class DeduplicationStrategy(BaseModel):
    """Deduplication pruning strategy."""

    enabled: bool = True


class SupersedeWritesStrategy(BaseModel):
    """Supersede writes pruning strategy."""

    enabled: bool = True
    aggressive: bool = False


class PurgeErrorsStrategy(BaseModel):
    """Purge errors pruning strategy."""

    enabled: bool = True
    turns: Annotated[int, Field(ge=1, le=20)] = 5


class PruningStrategies(BaseModel):
    """Pruning strategies configuration."""

    deduplication: Optional[DeduplicationStrategy] = None
    supersede_writes: Optional[SupersedeWritesStrategy] = None
    purge_errors: Optional[PurgeErrorsStrategy] = None


class DynamicContextPruningConfig(BaseModel):
    """Dynamic context pruning configuration."""

    enabled: bool = False
    notification: Literal["off", "minimal", "detailed"] = "detailed"
    turn_protection: Optional[TurnProtectionConfig] = None
    protected_tools: List[str] = [
        "task",
        "todowrite",
        "todoread",
        "lsp_rename",
        "session_read",
        "session_write",
        "session_search",
    ]
    strategies: Optional[PruningStrategies] = None


class AdvancedFallbackConfig(BaseModel):
    """Advanced Model Fallback System configuration.

    Ported from OpenClaw's model-fallback.ts.
    Enables multi-key rotation, cooldown tracking, and intelligent
    model fallback chains.

    Enable via experimental.advanced_fallback: true
    """

    enabled: bool = False
    fallback_models: List[str] = Field(
        default_factory=list,
        description="Fallback model chain (e.g., ['openai/gpt-5', 'google/gemini-2.5'])",
    )
    use_auth_profiles: bool = True
    probe_enabled: bool = True
    max_retries_per_model: Annotated[int, Field(ge=1, le=10)] = 2
    max_total_attempts: Annotated[int, Field(ge=1, le=50)] = 10

    class Config:
        extra = "allow"


class ExperimentalConfig(BaseModel):
    """Experimental feature flags configuration."""

    model_config = ConfigDict(extra="allow")

    aggressive_truncation: bool = False
    auto_resume: bool = False
    preemptive_compaction: bool = False
    truncate_all_tool_outputs: bool = False
    dynamic_context_pruning: Optional[DynamicContextPruningConfig] = None
    task_system: bool = False
    plugin_load_timeout_ms: Annotated[int, Field(ge=1000)] = 10000
    safe_hook_creation: bool = True
    disable_omo_env: bool = False
    hashline_edit: bool = False
    model_fallback_title: bool = False
    max_tools: Annotated[int, Field(ge=1)] = 128
    advanced_fallback: Optional[AdvancedFallbackConfig] = None

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature flag is enabled."""
        return getattr(self, feature, False)
