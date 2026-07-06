import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import RateLimitConfig
from .backends.base import RateLimitBackend
from .backends.memory import MemoryBackend


@dataclass
class RateLimitResult:
    allowed: bool
    tokens_remaining: int
    retry_after_seconds: float
    key: str


class RateLimitExceeded(Exception):
    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(
            f"Rate limit exceeded for key '{result.key}', "
            f"retry after {result.retry_after_seconds:.1f}s"
        )


class RateLimitService:
    def __init__(self, config: RateLimitConfig, backend: Optional[RateLimitBackend] = None):
        self.config = config
        self._backend = backend or self._init_backend()
        self._key_prefix = config.key_prefix

    def _init_backend(self) -> RateLimitBackend:
        if self.config.backend == "redis":
            from .backends.redis_backend import RedisBackend
            if not self.config.redis_url:
                raise ValueError("redis_url is required for redis backend")
            return RedisBackend(self.config.redis_url)
        return MemoryBackend()

    def _namespaced(self, key: str) -> str:
        return f"{self._key_prefix}:{key}" if self._key_prefix else key

    def check(
        self,
        key: str,
        capacity: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cost: int = 1,
    ) -> RateLimitResult:
        capacity = capacity if capacity is not None else self.config.default_capacity
        window_seconds = window_seconds if window_seconds is not None else self.config.default_window_seconds

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

    def limit(
        self,
        key_func: Callable[..., str],
        capacity: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cost: int = 1,
    ):
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                key = key_func(*args, **kwargs)
                result = self.check(key, capacity=capacity, window_seconds=window_seconds, cost=cost)
                if not result.allowed:
                    raise RateLimitExceeded(result)
                return func(*args, **kwargs)
            return wrapper
        return decorator
