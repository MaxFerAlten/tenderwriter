"""Ralph Loop Configuration.

Based on oh-my-openagent's RalphLoopConfigSchema.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


class RalphLoopConfig(BaseModel):
    """Ralph loop functionality configuration."""

    enabled: bool = False
    default_max_iterations: Annotated[int, Field(ge=1, le=1000)] = 100
    state_dir: Optional[str] = None
    default_strategy: Literal["reset", "continue"] = "continue"
