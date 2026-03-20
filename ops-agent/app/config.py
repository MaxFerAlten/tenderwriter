"""Configuration for the internal ops agent."""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ops_agent_host: str = "0.0.0.0"
    ops_agent_port: int = 8070
    ops_agent_token: str = ""
    ops_allowed_prefix: str = "tw-"
    ops_frontend_container: str = "tw-frontend"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_token(self) -> "Settings":
        if not self.ops_agent_token.strip():
            raise ValueError("OPS_AGENT_TOKEN is required")
        if not self.ops_allowed_prefix.strip():
            raise ValueError("OPS_ALLOWED_PREFIX is required")
        if not self.ops_frontend_container.strip():
            raise ValueError("OPS_FRONTEND_CONTAINER is required")
        return self


settings = Settings()
