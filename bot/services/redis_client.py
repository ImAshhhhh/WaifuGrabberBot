"""Async Redis client wrapper."""
from __future__ import annotations

import redis.asyncio as redis
from bot.config import settings

_redis: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8",
            max_connections=50,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


def get_redis() -> redis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis
