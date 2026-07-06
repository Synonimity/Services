import functools
import hashlib
import json
import time
from typing import Any, Callable, Optional

from .config import CacheConfig
from .backends.base import CacheBackend
from .backends.memory import MemoryBackend


class CacheService:
    def __init__(self, config: CacheConfig, backend: Optional[CacheBackend] = None):
        self.config = config
        self._backend = backend or self._init_backend()
        self._key_prefix = config.key_prefix

    def _init_backend(self) -> CacheBackend:
        if self.config.backend == "redis":
            from .backends.redis_backend import RedisBackend
            if not self.config.redis_url:
                raise ValueError("redis_url is required for redis backend")
            return RedisBackend(self.config.redis_url)
        return MemoryBackend()

    def _namespaced(self, key: str) -> str:
        return f"{self._key_prefix}:{key}" if self._key_prefix else key

    def get(self, key: str, default: Any = None) -> Any:
        raw = self._backend.get(self._namespaced(key))
        if raw is None:
            return default
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.config.default_ttl_seconds
        self._backend.set(self._namespaced(key), json.dumps(value, default=str), ttl)

    def delete(self, key: str) -> None:
        self._backend.delete(self._namespaced(key))

    def delete_prefix(self, prefix: str) -> int:
        return self._backend.delete_prefix(self._namespaced(prefix))

    def clear(self) -> None:
        self._backend.clear()

    def cached(self, ttl_seconds: Optional[int] = None, key_prefix: Optional[str] = None):
        def decorator(func: Callable) -> Callable:
            prefix = key_prefix or f"fn:{func.__module__}.{func.__qualname__}"

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                cache_key = self._build_function_key(prefix, args, kwargs)
                cached_value = self.get(cache_key, default=_MISSING)
                if cached_value is not _MISSING:
                    return cached_value

                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl_seconds=ttl_seconds)
                return result

            wrapper._synon_cache_prefix = prefix
            return wrapper
        return decorator

    def invalidate_function(self, decorated_func: Callable, *args, **kwargs) -> None:
        prefix = getattr(decorated_func, "_synon_cache_prefix", None)
        if prefix is None:
            raise ValueError("Function must be decorated with @cache.cached")
        cache_key = self._build_function_key(prefix, args, kwargs)
        self.delete(cache_key)

    def invalidate_all_for_function(self, decorated_func: Callable) -> int:
        prefix = getattr(decorated_func, "_synon_cache_prefix", None)
        if prefix is None:
            raise ValueError("Function must be decorated with @cache.cached")
        return self.delete_prefix(prefix)

    @staticmethod
    def _build_function_key(prefix: str, args: tuple, kwargs: dict) -> str:
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}:{digest}"


class _Missing:
    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
