"""
synon_cache.backends.memory

Zero-infra default backend. Stores everything in a plain dict in the
current process's memory.

IMPORTANT LIMITATION: this cache is per-process. If your app runs
multiple workers/processes (e.g. multiple uvicorn workers, or
separate instances behind a load balancer), each one has its OWN
cache — they don't share state. That's fine for a single-process dev
setup or a small product, but the moment you scale to multiple
workers, cached values can go stale inconsistently between them
(worker A invalidates its copy, worker B still serves the old one).
Switch to the Redis backend once that matters.
"""

import threading
import time
from typing import Optional

from .base import CacheBackend


class MemoryBackend(CacheBackend):
    def __init__(self):
        # (value, expires_at_epoch_or_None)
        self._store: dict[str, tuple[str, Optional[float]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.time() >= expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: Optional[int]) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds is not None else None
        with self._lock:
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            matching = [k for k in self._store if k.startswith(prefix)]
            for k in matching:
                del self._store[k]
            return len(matching)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
