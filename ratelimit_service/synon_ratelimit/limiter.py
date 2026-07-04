"""
synon_ratelimit.limiter

The public interface. Wraps whichever RateLimitBackend is configured.

    from synon_ratelimit import RateLimiter

    limiter = RateLimiter()  # uses RATELIMIT_BACKEND env var

    # Explicit check
    result = limiter.check("user:42", capacity=10, window_seconds=60)
    if not result.allowed:
        ...  # reject, result.retry_after_seconds tells you how long to wait

    # Decorator — for FastAPI routes or any callable, keyed on a
    # function you provide that extracts the rate-limit key from the
    # call's arguments (e.g. the user ID, IP address, license key)
    @limiter.limit(capacity=5, window_seconds=60, key_func=lambda request: request.client.host)
    def my_route(request): ...
"""

import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import config
from .backends.base import RateLimitBackend
from .backends.memory import MemoryBackend


@dataclass
class RateLimitResult:
    allowed: bool
    tokens_remaining: int
    retry_after_seconds: float
    key: str


class RateLimitExceeded(Exception):
    """
    Raised by the decorator when a call is rejected. Catch this in
    your FastAPI exception handler (or framework of choice) to return
    a proper 429. Carries the same info as RateLimitResult so the
    handler can set a Retry-After header.
    """

    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(
            f"Rate limit exceeded for key '{result.key}', "
            f"retry after {result.retry_after_seconds:.1f}s"
        )


class RateLimiter:
    def __init__(self, backend: Optional[RateLimitBackend] = None, key_prefix: Optional[str] = None):
        self._backend = backend or self._default_backend()
        self._key_prefix = key_prefix if key_prefix is not None else config.RATELIMIT_KEY_PREFIX

    @staticmethod
    def _default_backend() -> RateLimitBackend:
        if config.RATELIMIT_BACKEND == "redis":
            from .backends.redis_backend import RedisBackend

            return RedisBackend(config.REDIS_URL)
        return MemoryBackend()

    def _namespaced(self, key: str) -> str:
        return f"{self._key_prefix}:{key}" if self._key_prefix else key

    # ------------------------------------------------------------------
    # Explicit check
    # ------------------------------------------------------------------

    def check(
        self,
        key: str,
        capacity: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check (and consume, if allowed) against the bucket for `key`.

        Args:
            key: identifies WHO/WHAT is being limited — e.g.
                 "user:42", "ip:1.2.3.4", "license:K7XJ-..."
            capacity: max tokens in the bucket (defaults to
                      RATELIMIT_DEFAULT_CAPACITY)
            window_seconds: time for a full refill (defaults to
                            RATELIMIT_DEFAULT_WINDOW_SECONDS)
            cost: tokens this specific call consumes — use >1 for
                  operations you want to weight as "more expensive"
                  than a normal request
        """
        capacity = capacity if capacity is not None else config.RATELIMIT_DEFAULT_CAPACITY
        window_seconds = window_seconds if window_seconds is not None else config.RATELIMIT_DEFAULT_WINDOW_SECONDS

        namespaced_key = self._namespaced(key)
        allowed, remaining, retry_after = self._backend.consume(
            key=namespaced_key,
            capacity=capacity,
            refill_window_seconds=window_seconds,
            tokens_requested=cost,
            now=time.time(),
        )
        return RateLimitResult(
            allowed=allowed,
            tokens_remaining=remaining,
            retry_after_seconds=retry_after,
            key=key,
        )

    def reset(self, key: str) -> None:
        self._backend.reset(self._namespaced(key))

    def clear(self) -> None:
        self._backend.clear()

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def limit(
        self,
        key_func: Callable[..., str],
        capacity: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cost: int = 1,
    ):
        """
        Decorator: checks the rate limit before calling the wrapped
        function, raising RateLimitExceeded if over the limit.

        `key_func` receives the SAME arguments the wrapped function
        is called with, and must return a string identifying who/what
        to rate-limit. This is deliberately explicit rather than
        guessing — your function's arguments could be a FastAPI
        Request, a user ID, a license key, anything; you decide which
        argument identifies the caller.

            @limiter.limit(key_func=lambda request: f"ip:{request.client.host}", capacity=20, window_seconds=60)
            def handle_request(request):
                ...
        """

        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                key = key_func(*args, **kwargs)
                result = self.check(key, capacity=capacity, window_seconds=window_seconds, cost=cost)
                if not result.allowed:
                    raise RateLimitExceeded(result)
                return func(*args, **kwargs)

            return wrapper

        return decorator
