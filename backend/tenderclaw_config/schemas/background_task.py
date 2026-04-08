"""Background Task Configuration.

Based on oh-my-openagent's BackgroundTaskConfigSchema.
"""

from __future__ import annotations

from typing import Annotated, Dict, Optional

from pydantic import BaseModel, Field


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for background tasks."""

    enabled: bool = True
    max_tool_calls: Annotated[int, Field(ge=10)] = 200
    consecutive_threshold: Annotated[int, Field(ge=5)] = 50


class BackgroundTaskConfig(BaseModel):
    """Background task execution configuration."""

    default_concurrency: Annotated[int, Field(ge=1)] = 3
    provider_concurrency: Optional[Dict[str, int]] = None
    model_concurrency: Optional[Dict[str, int]] = None
    max_depth: Annotated[int, Field(ge=1)] = 10
    max_descendants: Annotated[int, Field(ge=1)] = 50
    stale_timeout_ms: Annotated[int, Field(ge=60000)] = 180000
    message_staleness_timeout_ms: Annotated[int, Field(ge=60000)] = 1800000
    task_ttl_ms: Annotated[int, Field(ge=300000)] = 1800000
    session_gone_timeout_ms: Annotated[int, Field(ge=10000)] = 60000
    sync_poll_timeout_ms: Annotated[int, Field(ge=60000)] = 300000
    max_tool_calls: Annotated[int, Field(ge=10)] = 200
    circuit_breaker: Optional[CircuitBreakerConfig] = None
