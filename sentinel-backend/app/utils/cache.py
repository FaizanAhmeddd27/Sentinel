import json
import hashlib
from typing import Any, Optional, Callable
from functools import wraps
from loguru import logger
from app.config import settings


def _get_redis():
    """Get async Redis connection."""
    import redis.asyncio as aioredis
    return aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )


async def cache_set(key: str, value: Any, ttl: int = None) -> bool:
    """Set a value in Redis cache."""
    try:
        r = _get_redis()
        serialized = json.dumps(value, default=str)
        ttl = ttl or settings.redis_cache_ttl
        await r.setex(key, ttl, serialized)
        await r.aclose()
        return True
    except Exception as e:
        logger.warning(f"Cache SET failed for key={key}: {e}")
        return False


async def cache_get(key: str) -> Optional[Any]:
    """Get a value from Redis cache. Returns None on miss or error."""
    try:
        r = _get_redis()
        value = await r.get(key)
        await r.aclose()
        if value is None:
            return None
        return json.loads(value)
    except Exception as e:
        logger.warning(f"Cache GET failed for key={key}: {e}")
        return None


async def cache_delete(key: str) -> bool:
    """Delete a key from cache."""
    try:
        r = _get_redis()
        await r.delete(key)
        await r.aclose()
        return True
    except Exception as e:
        logger.warning(f"Cache DELETE failed for key={key}: {e}")
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns count deleted."""
    try:
        r = _get_redis()
        keys = await r.keys(pattern)
        if keys:
            deleted = await r.delete(*keys)
            await r.aclose()
            return deleted
        await r.aclose()
        return 0
    except Exception as e:
        logger.warning(f"Cache DELETE pattern failed for {pattern}: {e}")
        return 0


async def cache_increment(key: str, amount: int = 1, ttl: int = 3600) -> int:
    """Increment a counter in cache. Useful for rate limiting."""
    try:
        r = _get_redis()
        value = await r.incr(key, amount)
        if value == amount:  # First time — set TTL
            await r.expire(key, ttl)
        await r.aclose()
        return value
    except Exception as e:
        logger.warning(f"Cache INCREMENT failed for key={key}: {e}")
        return 0


def make_cache_key(*parts: Any) -> str:
    """Build a deterministic cache key from parts."""
    raw = ":".join(str(p) for p in parts)
    if len(raw) > 200:
        raw = hashlib.md5(raw.encode()).hexdigest()
    return f"sentinel:{raw}"


def cached(ttl: int = None, key_prefix: str = ""):
    """
    Decorator for caching async function results in Redis.

    Usage:
        @cached(ttl=300, key_prefix="dashboard")
        async def get_dashboard_stats(user_id: str) -> dict:
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name + args
            key_parts = [key_prefix or func.__name__] + [str(a) for a in args]
            key_parts += [f"{k}={v}" for k, v in sorted(kwargs.items())]
            cache_key = make_cache_key(*key_parts)

            # Try cache first
            cached_value = await cache_get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache HIT: {cache_key}")
                return cached_value

            # Cache miss — call function
            logger.debug(f"Cache MISS: {cache_key}")
            result = await func(*args, **kwargs)

            # Store in cache
            await cache_set(cache_key, result, ttl=ttl)
            return result

        return wrapper
    return decorator


# ─── Pre-defined cache keys for hot data ─────────────────────────────────────

CACHE_KEYS = {
    "dashboard_stats": "sentinel:dashboard:stats",
    "open_incidents_count": "sentinel:incidents:open_count",
    "reconciliation_queue": "sentinel:reconciliation:queue_summary",
    "system_status": "sentinel:system:status",
    "roi_metrics": "sentinel:analytics:roi",
}


async def get_dashboard_cache() -> Optional[dict]:
    """Get cached dashboard stats."""
    return await cache_get(CACHE_KEYS["dashboard_stats"])


async def set_dashboard_cache(data: dict) -> bool:
    """Cache dashboard stats for 60 seconds."""
    return await cache_set(CACHE_KEYS["dashboard_stats"], data, ttl=60)


async def invalidate_incident_cache():
    """Invalidate all incident-related cache entries."""
    await cache_delete_pattern("sentinel:incidents:*")
    await cache_delete(CACHE_KEYS["dashboard_stats"])
    logger.debug("Incident cache invalidated")