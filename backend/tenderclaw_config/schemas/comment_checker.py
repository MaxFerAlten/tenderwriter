"""Comment Checker Configuration.

Based on oh-my-openagent's CommentCheckerConfigSchema.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class CommentCheckerConfig(BaseModel):
    """AI slop comment detection configuration."""

    custom_prompt: Optional[str] = Field(
        default=None,
        description="Custom prompt to replace the default warning message. Use {{comments}} placeholder for detected comments XML.",
    )
