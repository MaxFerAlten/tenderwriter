"""Prompt builder (Wave 1) — centralizes prompt assembly."""

from __future__ import annotations

from backend.core.system_prompt import build_system_prompt


def build_runtime_system_prompt(working_directory: str = ".", append: str = "") -> str:
    """Return the full system prompt for a runtime session."""
    return build_system_prompt(working_directory=working_directory, append=append)
