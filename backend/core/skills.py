"""Enhanced Skills Loader — Wave 2 skill discovery and injection.

Skills are directories containing SKILL.md files. This module provides
rich parsing of SKILL.md (trigger, agents, flow, rules) and a structured
Skill registry for the runtime. It replaces the basic legacy implementation
with a full parser and a skill registry that can be queried at runtime.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

logger = logging.getLogger("tenderclaw.core.skills")

DEFAULT_SKILLS_PATHS = [
    Path(__file__).parent.parent.parent / "skills",
    Path(r"d:\MY_AI\claude-code\superpowers\skills"),
]


@dataclass
class Skill:
    """Structured skill metadata parsed from SKILL.md."""
    name: str
    path: Path
    trigger: str = ""
    description: str = ""
    agents: list[str] = field(default_factory=list)
    flow: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    raw: str = ""


class SkillRegistry:
    """In-memory registry of discovered skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def by_agent(self, agent: str) -> list[Skill]:
        return [s for s in self._skills.values() if agent in s.agents]

    def __len__(self) -> int:
        return len(self._skills)


# Global singleton registry
_skill_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
        discover_skills(_skill_registry)
    return _skill_registry


def discover_skills(registry: SkillRegistry, paths: list[Path] | None = None) -> None:
    """Scan SKILLS_PATHS and register all discovered skills."""
    search_paths = paths or DEFAULT_SKILLS_PATHS
    for base_path in search_paths:
        if not base_path.exists():
            logger.debug("Skills path does not exist: %s", base_path)
            continue
        for skill_dir in base_path.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skill = parse_skill(skill_dir.name, skill_md)
                registry.register(skill)
                logger.debug("Registered skill: %s", skill.name)
            except Exception as exc:
                logger.warning("Failed to parse skill %s: %s", skill_dir.name, exc)


def parse_skill(name: str, skill_md: Path) -> Skill:
    """Parse a SKILL.md file into a structured Skill object."""
    content = skill_md.read_text("utf-8")
    lines = content.splitlines()

    skill = Skill(name=name, path=skill_md, raw=content)

    # Extract ## Sections
    current_section = ""
    section_lines: list[str] = []

    def flush():
        nonlocal current_section, section_lines
        cn = current_section.lower().strip()
        if cn == "trigger":
            skill.trigger = "\n".join(section_lines).strip()
        elif cn == "description":
            skill.description = "\n".join(section_lines).strip()
        elif cn == "agents":
            skill.agents = [l.strip().lstrip("- *") for l in section_lines if l.strip()]
        elif cn == "flow":
            skill.flow = [re.sub(r"^\d+\.\s*", "", l).strip() for l in section_lines if l.strip()]
        elif cn == "rules":
            skill.rules = [l.strip().lstrip("- ") for l in section_lines if l.strip()]

    for line in lines:
        if line.startswith("## "):
            flush()
            current_section = line[3:].strip()
            section_lines = []
        elif line.startswith("# ") and not current_section:
            # Title line — use as description fallback
            skill.description = line[1:].strip().lstrip("/").strip()
        else:
            section_lines.append(line)

    flush()
    # Fallback description
    if not skill.description:
        skill.description = "Specialized workflow skill."
    return skill


def list_available_skills() -> list[dict[str, Any]]:
    """Return a list of all skills found in the SKILLS_PATHS (legacy dict format)."""
    reg = get_registry()
    return [
        {
            "name": s.name,
            "path": str(s.path),
            "description": s.description,
            "trigger": s.trigger,
            "agents": s.agents,
        }
        for s in reg.all()
    ]


def build_skills_instruction() -> str:
    """Consolidate all skills into a prompt section for the agent (enhanced format)."""
    skills = list_available_skills()
    if not skills:
        return ""

    instruction = "\n## Superpowers Skills\n"
    instruction += "You have access to specialized 'skills' for complex tasks.\n"
    instruction += "If a task matches one of these, you MUST read the SKILL.md file before proceeding:\n"

    for s in skills:
        trigger = f" (trigger: {s['trigger']})" if s.get("trigger") else ""
        instruction += f"- **{s['name']}**{trigger}: {s['description']}\n"

    instruction += "\nTo read a skill, use `Read` on its path listed above."
    return instruction


def get_skill_by_name(name: str) -> Skill | None:
    return get_registry().get(name)


def match_trigger(text: str) -> list[Skill]:
    """Return skills whose trigger pattern matches the given text."""
    reg = get_registry()
    matched = []
    for s in reg.all():
        if s.trigger and s.trigger.lstrip("/") in text:
            matched.append(s)
    return matched
