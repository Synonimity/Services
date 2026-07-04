"""
synon_ratelimit.backends.memory

Zero-infra default backend. Token bucket state lives in a plain dict
in the current process's memory.

SAME LIMITATION AS synon_cache.backends.memory: per-process. Multiple
workers each enforce their OWN limit independently — a "10 req/min"
limit becomes "10 req/min PER WORKER" if you run 4 workers. Fine for
a single-process app; switch to Redis once that distinction matters
(e.g. protecting a shared downstream resource, or enforcing a limit
that must hold regardless of how many workers are running).
"""

import threading
from typing import Optional

from .base import RateLimitBackend


class MemoryBackend(RateLimitBackend):
    def __init__(self):
        # key -> (tokens_remaining: float, last_refill: float)
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def consume(
        self,
        key: str,
        capacity: int,
        refill_window_seconds: int,
        tokens_requested: int,
        now: float,
    ) -> tuple[bool, int, float]:
        refill_rate = capacity / refill_window_seconds  # tokens per second

        with self._lock:
            tokens, last_refill = self._buckets.get(key, (float(capacity), now))

            # Refill based on elapsed time since last check, capped at capacity
            elapsed = max(0.0, now - last_refill)
            tokens = min(capacity, tokens + elapsed * refill_rate)

            if tokens >= tokens_requested:
                tokens -= tokens_requested
                self._buckets[key] = (tokens, now)
                return True, int(tokens), 0.0
            else:
                # How long until enough tokens have refilled
                deficit = tokens_requested - tokens
                retry_after = deficit / refill_rate
                self._buckets[key] = (tokens, now)
                return False, int(tokens), retry_after

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._buckets.clear()
