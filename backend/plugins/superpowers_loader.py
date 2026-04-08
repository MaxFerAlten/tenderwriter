"""Superpowers Loader — parse agent and command definitions from markdown files.

Supports the frontmatter-based format used by the superpowers library:

    ---
    name: code-reviewer
    description: Expert code reviewer
    model: claude-sonnet-4-20250514
    ---
    You are an expert code reviewer...
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("tenderclaw.plugins.superpowers_loader")


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter from markdown body.

    Returns (metadata_dict, body_text).
    If no frontmatter is found, returns ({}, full_text).
    """
    # Match --- block at the very start of the file
    pattern = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)
    match = pattern.match(text)
    if not match:
        return {}, text.strip()

    yaml_block, body = match.groups()
    metadata: dict[str, Any] = {}

    # Minimal YAML parser (key: value lines, no nested structures needed)
    for line in yaml_block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body.strip()


def load_agents_from_markdown(agents_dir: Path) -> list[dict[str, Any]]:
    """Parse all *.md files in agents_dir and return agent descriptor dicts.

    Each dict has keys: name, description, model, system_prompt.
    """
    agents: list[dict[str, Any]] = []

    if not agents_dir.exists():
        logger.debug("Agents dir not found: %s", agents_dir)
        return agents

    for md_file in sorted(agents_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(text)

            name = meta.get("name") or md_file.stem
            # Sanitize: lowercase, replace spaces/hyphens with underscores
            name = re.sub(r"[\s\-]+", "_", name.lower())

            agents.append({
                "name": name,
                "description": meta.get("description") or f"Superpowers agent: {name}",
                "model": meta.get("model") or "claude-sonnet-4-20250514",
                "system_prompt": body or f"You are {name}, a specialist agent.",
                "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
            })
            logger.debug("Loaded superpowers agent from %s: %s", md_file.name, name)
        except Exception as exc:
            logger.warning("Failed to parse agent file %s: %s", md_file.name, exc)

    return agents


def load_commands_from_markdown(commands_dir: Path) -> list[dict[str, Any]]:
    """Parse all *.md files in commands_dir and return command descriptor dicts.

    Each dict has keys: name, description, body.
    """
    commands: list[dict[str, Any]] = []

    if not commands_dir.exists():
        logger.debug("Commands dir not found: %s", commands_dir)
        return commands

    for md_file in sorted(commands_dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            meta, body = _parse_frontmatter(text)

            name = meta.get("name") or md_file.stem
            name = re.sub(r"[\s\-]+", "_", name.lower())

            commands.append({
                "name": f"superpowers__{name}",
                "description": meta.get("description") or f"Superpowers command: {name}",
                "body": body,
            })
            logger.debug("Loaded superpowers command: %s", name)
        except Exception as exc:
            logger.warning("Failed to parse command file %s: %s", md_file.name, exc)

    return commands
