"""
synon_cache.backends.redis_backend

Opt-in backend for when the in-process MemoryBackend's limitations
(per-process only, lost on restart) actually matter — multi-worker
deployments, or caching that needs to survive a restart.

Requires `redis` package and REDIS_URL to be set. Import is deferred
inside __init__ so projects that never touch Redis don't need the
package installed at all.
"""

from typing import Optional

from .base import CacheBackend


class RedisBackend(CacheBackend):
    def __init__(self, redis_url: str):
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "synon_cache: RedisBackend requires the 'redis' package. "
                "Install it with: pip install redis"
            ) from exc

        if not redis_url:
            raise ValueError("synon_cache: RedisBackend requires a non-empty redis_url")

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl_seconds: Optional[int]) -> None:
        if ttl_seconds is not None:
            self._client.set(key, value, ex=ttl_seconds)
        else:
            self._client.set(key, value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        # SCAN rather than KEYS — KEYS blocks the whole Redis instance
        # on large keyspaces, SCAN doesn't. Worth doing correctly even
        # in a template, since this is exactly the kind of detail that
        # bites in production and not in dev.
        count = 0
        for key in self._client.scan_iter(match=f"{prefix}*"):
            self._client.delete(key)
            count += 1
        return count

    def clear(self) -> None:
        self._client.flushdb()
