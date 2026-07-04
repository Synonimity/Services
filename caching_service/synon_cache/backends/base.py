"""
synon_cache.backends.base

The plug-in interface. Cache (in cache.py) never knows whether it's
talking to an in-process dict or Redis — it just calls these methods.
Same pattern as synon_webhooks.verifiers.base.
"""

from abc import ABC, abstractmethod
from typing import Optional


class CacheBackend(ABC):
    """
    Subclass this to add a new storage backend. All methods deal in
    raw strings — serialization (JSON, pickle, whatever) happens in
    Cache, not here, so backends stay dumb and swappable.
    """

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Returns the stored value, or None if missing/expired."""
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: Optional[int]) -> None:
        """
        Stores value under key. ttl_seconds=None means "no expiry" —
        only removed by explicit delete().
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        """Removes a key. No-op if it doesn't exist — never raises."""
        raise NotImplementedError

    @abstractmethod
    def delete_prefix(self, prefix: str) -> int:
        """
        Removes all keys starting with `prefix`. Used for bulk
        invalidation (e.g. "blow away every cached page for this
        product"). Returns the count removed.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Removes everything this backend is holding. Mostly for tests."""
        raise NotImplementedError
