"""TenderWriter — Redis Client."""

import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_timeout=settings.redis_socket_timeout_seconds,
    socket_connect_timeout=settings.redis_connect_timeout_seconds,
    health_check_interval=settings.redis_health_check_interval_seconds,
    retry_on_timeout=True,
)


async def get_redis():
    """Dependency for getting the Redis client."""
    return redis_client


async def close_redis() -> None:
    """Close the shared Redis client cleanly during shutdown."""
    await redis_client.aclose()
