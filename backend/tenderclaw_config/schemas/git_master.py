"""Git Master Configuration.

Based on oh-my-openagent's GitMasterConfigSchema.
"""

from __future__ import annotations

import re
from typing import Literal, Optional, Union

from pydantic import BaseModel, field_validator


class GitMasterConfig(BaseModel):
    """Git Master skill configuration."""

    commit_footer: Union[bool, str] = True
    include_co_authored_by: bool = True
    git_env_prefix: str = "GIT_MASTER=1"

    @field_validator("git_env_prefix")
    @classmethod
    def validate_git_env_prefix(cls, v: str) -> str:
        """Validate that git_env_prefix doesn't contain shell metacharacters."""
        shell_chars = re.compile(r"[;&|`$(){}[\]!?*<>\"'\\]")
        if shell_chars.search(v):
            raise ValueError("git_env_prefix contains shell metacharacters")
        return v

    def get_commit_footer(self) -> Optional[str]:
        """Get the commit footer text."""
        if isinstance(self.commit_footer, bool):
            return "Ultraworked with TenderClaw" if self.commit_footer else None
        return self.commit_footer

    def get_git_env(self) -> Dict[str, str]:
        """Get environment variables for git commands."""
        if not self.git_env_prefix:
            return {}
        if "=" in self.git_env_prefix:
            key, value = self.git_env_prefix.split("=", 1)
            return {key: value}
        return {self.git_env_prefix: "1"}
