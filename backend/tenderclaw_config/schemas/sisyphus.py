"""Sisyphus Configuration.

Based on oh-my-openagent's SisyphusConfigSchema.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SisyphusTasksConfig(BaseModel):
    """Sisyphus tasks configuration."""

    storage_path: Optional[str] = None
    task_list_id: Optional[str] = None
    claude_code_compat: bool = False


class SisyphusConfig(BaseModel):
    """Sisyphus orchestrator configuration."""

    tasks: Optional[SisyphusTasksConfig] = None
