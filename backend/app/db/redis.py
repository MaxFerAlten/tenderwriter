"""
TenderWriter — Redis Client
"""

import redis.asyncio as redis
from app.config import settings

# Create a global Redis client
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

async def get_redis():
    """Dependency for getting the Redis client."""
    return redis_client
