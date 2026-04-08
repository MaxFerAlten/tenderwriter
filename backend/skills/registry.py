"""Skeleton skill registry (placeholder)."""

from __future__ import annotations

class SkillRegistry:
    def __init__(self):
        self._skills = {}

    def register(self, name: str, data=None):
        self._skills[name] = data or {}

    def has(self, name: str) -> bool:
        return name in self._skills

    def get(self, name: str):
        return self._skills.get(name)
