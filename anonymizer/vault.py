from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import defaultdict
from typing import Any

try:
    from redis.asyncio import from_url as redis_from_url
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover
    redis_from_url = None
    RedisError = Exception


class RedisVault:
    def __init__(self, redis_url: str, default_ttl_seconds: int = 3600):
        self.redis_url = redis_url
        self.default_ttl_seconds = default_ttl_seconds
        self._redis = None
        self._memory_sessions: dict[str, tuple[float, dict[str, Any]]] = {}
        self._memory_config: dict[str, Any] = {}
        self._memory_stats: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.redis_url.startswith("memory://") or redis_from_url is None:
            return
        client = redis_from_url(self.redis_url, decode_responses=True)
        try:
            await client.ping()
        except RedisError:
            await client.aclose()
            self._redis = None
            return
        self._redis = client

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    async def create_session_id(self) -> str:
        return uuid.uuid4().hex

    async def store_session(
        self,
        session_id: str,
        mapping: dict[str, str],
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> None:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        if ttl <= 0:
            if self._redis is not None:
                await self._redis.delete(f"session:{session_id}")
                return
            async with self._lock:
                self._memory_sessions.pop(session_id, None)
            return
        payload = {
            "mapping": mapping,
            "metadata": metadata or {},
            "created_at": int(time.time()),
        }
        if self._redis is not None:
            await self._redis.setex(f"session:{session_id}", ttl, json.dumps(payload))
            return
        expires_at = time.time() + ttl
        async with self._lock:
            self._memory_sessions[session_id] = (expires_at, payload)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        if self._redis is not None:
            payload = await self._redis.get(f"session:{session_id}")
            return json.loads(payload) if payload else None
        async with self._lock:
            item = self._memory_sessions.get(session_id)
            if item is None:
                return None
            expires_at, payload = item
            if expires_at <= time.time():
                self._memory_sessions.pop(session_id, None)
                return None
            return payload

    async def load_config(self) -> dict[str, Any]:
        if self._redis is not None:
            payload = await self._redis.get("config:default")
            return json.loads(payload) if payload else {}
        async with self._lock:
            return dict(self._memory_config)

    async def save_config(self, config: dict[str, Any]) -> dict[str, Any]:
        if self._redis is not None:
            await self._redis.set("config:default", json.dumps(config))
            return config
        async with self._lock:
            self._memory_config = dict(config)
        return config

    async def update_stats(self, **increments: int) -> dict[str, int]:
        if self._redis is not None:
            pipe = self._redis.pipeline()
            for key, value in increments.items():
                pipe.incrby(f"stats:{key}", value)
            await pipe.execute()
            return await self.get_stats()
        async with self._lock:
            for key, value in increments.items():
                self._memory_stats[key] += value
            return dict(self._memory_stats)

    async def get_stats(self) -> dict[str, int]:
        if self._redis is not None:
            keys = [
                "requests",
                "sessions",
                "entities_detected",
                "deanonymize_requests",
                "faking_requests",
            ]
            values = await asyncio.gather(
                *(self._redis.get(f"stats:{key}") for key in keys)
            )
            return {key: int(value or 0) for key, value in zip(keys, values)}
        async with self._lock:
            return dict(self._memory_stats)
