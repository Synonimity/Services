"""
Pluggable storage backends for synon_response_cache.

Deliberately minimal interface (get/set/delete) so this can be swapped
for `synon_cache` directly if you've already got that wired up in a
project - just write a thin adapter implementing CacheBackend around it.

InMemoryBackend is zero-setup (single process only, no TTL sweep - expired
entries are just skipped on read, not proactively evicted). RedisBackend
is the real answer for anything multi-instance.
"""

from abc import ABC, abstractmethod
from typing import Optional
import os
import time
import json


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        ...

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...


class InMemoryBackend(CacheBackend):
    """Zero-setup backend. Data lives only for the life of the process."""

    def __init__(self):
        self._store: dict = {}  # key -> (value, expires_at | None)

    def get(self, key: str) -> Optional[str]:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        expires_at = (time.time() + ttl_seconds) if ttl_seconds else None
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class RedisBackend(CacheBackend):
    """
    Requires the `redis` package and REDIS_URL env var.
    Recommended for anything running more than one process/instance.
    """

    def __init__(self, url: Optional[str] = None):
        try:
            import redis
        except ImportError as e:
            raise ImportError(
                "RedisBackend requires the 'redis' package: pip install redis"
            ) from e

        url = url or os.getenv("REDIS_URL")
        if not url:
            raise ValueError("REDIS_URL must be set to use RedisBackend.")

        self.client = redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[str]:
        return self.client.get(key)

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        if ttl_seconds:
            self.client.setex(key, ttl_seconds, value)
        else:
            self.client.set(key, value)

    def delete(self, key: str) -> None:
        self.client.delete(key)
