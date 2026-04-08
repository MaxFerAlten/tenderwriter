"""Category Configuration Schema.

Categories define default model and settings for different task types.
Based on oh-my-openagent's CategoryConfigSchema with 8 built-in categories.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


BuiltinCategoryName = Literal[
    "visual-engineering",
    "ultrabrain",
    "deep",
    "artistry",
    "quick",
    "unspecified-low",
    "unspecified-high",
    "writing",
]


class CategoryThinkingConfig(BaseModel):
    """Thinking configuration for category."""

    type: Literal["enabled", "disabled"] = "disabled"
    budget_tokens: Annotated[int, Field(ge=1024, le=200000)] = 32000


class CategoryConfig(BaseModel):
    """Category configuration with model, temperature, tools, etc."""

    model_config = ConfigDict(extra="allow")

    description: Optional[str] = Field(
        default=None,
        description="Human-readable description of the category's purpose",
    )
    model: Optional[str] = None
    fallback_models: Optional[List[str]] = None
    variant: Optional[str] = None
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.7
    top_p: Annotated[float, Field(ge=0, le=1)] = 1.0
    max_tokens: Annotated[int, Field(ge=1)] = 8192
    thinking: Optional[CategoryThinkingConfig] = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] = "medium"
    text_verbosity: Literal["low", "medium", "high"] = "medium"
    tools: Optional[Dict[str, bool]] = None
    prompt_append: Optional[str] = None
    max_prompt_tokens: Annotated[int, Field(gt=0)] = 16000
    is_unstable_agent: bool = False
    disable: bool = False


BUILTIN_CATEGORIES: Dict[str, CategoryConfig] = {
    "visual-engineering": CategoryConfig(
        description="Frontend, UI/UX, CSS, animations, and visual components",
        model="claude-sonnet-4-20250514",
        temperature=0.5,
        reasoning_effort="medium",
    ),
    "ultrabrain": CategoryConfig(
        description="Complex reasoning, architecture, deep analysis",
        model="claude-opus-4-20250514",
        temperature=0.3,
        reasoning_effort="high",
        max_tokens=16384,
    ),
    "deep": CategoryConfig(
        description="Deep investigation, research, thorough analysis",
        model="claude-opus-4-20250514",
        temperature=0.4,
        reasoning_effort="high",
    ),
    "artistry": CategoryConfig(
        description="Creative writing, content generation, marketing",
        model="claude-sonnet-4-20250514",
        temperature=0.9,
        reasoning_effort="low",
        text_verbosity="high",
    ),
    "quick": CategoryConfig(
        description="Fast, simple tasks, one-liners, small fixes",
        model="claude-haiku-4-20250707",
        temperature=0.5,
        reasoning_effort="none",
        max_tokens=2048,
    ),
    "unspecified-low": CategoryConfig(
        description="Low-priority unspecified tasks",
        model="claude-haiku-4-20250707",
        temperature=0.5,
    ),
    "unspecified-high": CategoryConfig(
        description="High-priority unspecified tasks",
        model="claude-sonnet-4-20250514",
        temperature=0.5,
    ),
    "writing": CategoryConfig(
        description="Writing, documentation, content creation",
        model="claude-sonnet-4-20250514",
        temperature=0.7,
        text_verbosity="high",
    ),
}


class CategoriesConfig(BaseModel):
    """Container for all category configurations."""

    model_config = ConfigDict(extra="allow")

    visual_engineering: Optional[CategoryConfig] = Field(
        default=None,
        description="Frontend, UI/UX, CSS, animations",
    )
    ultrabrain: Optional[CategoryConfig] = Field(
        default=None,
        description="Complex reasoning, architecture",
    )
    deep: Optional[CategoryConfig] = Field(
        default=None,
        description="Deep investigation, research",
    )
    artistry: Optional[CategoryConfig] = Field(
        default=None,
        description="Creative writing, content",
    )
    quick: Optional[CategoryConfig] = Field(
        default=None,
        description="Fast, simple tasks",
    )
    unspecified_low: Optional[CategoryConfig] = Field(
        default=None,
        alias="unspecified-low",
    )
    unspecified_high: Optional[CategoryConfig] = Field(
        default=None,
        alias="unspecified-high",
    )
    writing: Optional[CategoryConfig] = Field(
        default=None,
        description="Writing, documentation",
    )

    def get_category(self, name: str) -> Optional[CategoryConfig]:
        """Get category config by name, falling back to built-in."""
        name_mapping = {
            "visual-engineering": self.visual_engineering,
            "ultrabrain": self.ultrabrain,
            "deep": self.deep,
            "artistry": self.artistry,
            "quick": self.quick,
            "unspecified-low": self.unspecified_low,
            "unspecified-high": self.unspecified_high,
            "writing": self.writing,
        }
        if name in name_mapping:
            return name_mapping[name]
        if self.model_extra and name in self.model_extra:
            return CategoryConfig.model_validate(self.model_extra[name])
        if name in BUILTIN_CATEGORIES:
            return BUILTIN_CATEGORIES[name]
        return None

    def get_effective_category(self, name: str) -> CategoryConfig:
        """Get effective category config (with defaults from built-in)."""
        config = self.get_category(name)
        if config:
            return config
        return BUILTIN_CATEGORIES.get(name, CategoryConfig())

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump model with proper key naming."""
        data = super().model_dump(**kwargs)
        if "unspecified_low" in data and data["unspecified_low"] is not None:
            data["unspecified-low"] = data.pop("unspecified_low")
        if "unspecified_high" in data and data["unspecified_high"] is not None:
            data["unspecified-high"] = data.pop("unspecified_high")
        for key in list(data.keys()):
            if data[key] is None:
                del data[key]
        return data
