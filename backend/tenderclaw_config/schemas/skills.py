"""Skills Configuration Schema.

Based on oh-my-openagent's SkillsConfigSchema.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


SkillSource = Union[str, Dict[str, Any]]


class SkillDefinition(BaseModel):
    """Skill definition with metadata."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    description: Optional[str] = None
    template: Optional[str] = None
    from_skill: Optional[str] = Field(default=None, alias="from")
    model: Optional[str] = None
    agent: Optional[str] = None
    subtask: bool = False
    argument_hint: Optional[str] = None
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    allowed_tools: Optional[List[str]] = None
    disable: bool = False


SkillEntry = Union[bool, SkillDefinition]


class SkillsSourcesConfig(BaseModel):
    """Skills sources configuration."""

    path: str
    recursive: bool = True
    glob: Optional[str] = None


class SkillsConfig(BaseModel):
    """Skills configuration with sources and enable/disable lists."""

    model_config = ConfigDict(extra="allow")

    sources: Optional[List[Union[str, SkillsSourcesConfig]]] = None
    enable: Optional[List[str]] = None
    disable: Optional[List[str]] = None

    def get_enabled_skills(self, all_skills: List[str]) -> List[str]:
        """Get list of enabled skills."""
        if self.disable:
            disabled = set(self.disable)
            return [s for s in all_skills if s not in disabled]
        if self.enable:
            return self.enable
        return all_skills

    def is_skill_enabled(self, skill_name: str) -> bool:
        """Check if a specific skill is enabled."""
        if self.disable and skill_name in self.disable:
            return False
        if self.enable and skill_name not in self.enable:
            return False
        return True

    def get_sources(self) -> List[SkillSource]:
        """Get skill sources with defaults."""
        if self.sources:
            return self.sources
        return ["skills/", "./skills"]


BuiltinSkillName = Literal[
    "playwright",
    "agent-browser",
    "dev-browser",
    "frontend-ui-ux",
    "git-master",
]
