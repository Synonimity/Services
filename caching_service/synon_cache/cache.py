"""
synon_cache.cache

The public interface. Wraps whichever CacheBackend is configured —
the rest of your code never touches the backend directly.

    from synon_cache import Cache

    cache = Cache()  # uses CACHE_BACKEND env var, defaults to memory

    # Explicit calls
    cache.set("user:42", {"name": "Syn"}, ttl_seconds=60)
    user = cache.get("user:42")
    cache.delete("user:42")

    # Decorator — caches the return value, keyed on function name + args
    @cache.cached(ttl_seconds=300)
    def get_product_catalog(product_id: str):
        return expensive_supabase_query(product_id)

    # Manual invalidation hook — call this after a write that makes
    # cached reads stale (e.g. inside an UPDATE handler)
    cache.invalidate_function(get_product_catalog, product_id="kerfcut")
"""

import functools
import hashlib
import json
from typing import Any, Callable, Optional

from . import config
from .backends.base import CacheBackend
from .backends.memory import MemoryBackend


class Cache:
    def __init__(self, backend: Optional[CacheBackend] = None, key_prefix: Optional[str] = None):
        self._backend = backend or self._default_backend()
        self._key_prefix = key_prefix if key_prefix is not None else config.CACHE_KEY_PREFIX

    @staticmethod
    def _default_backend() -> CacheBackend:
        if config.CACHE_BACKEND == "redis":
            from .backends.redis_backend import RedisBackend

            return RedisBackend(config.REDIS_URL)
        return MemoryBackend()

    def _namespaced(self, key: str) -> str:
        return f"{self._key_prefix}:{key}" if self._key_prefix else key

    # ------------------------------------------------------------------
    # Explicit calls
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        raw = self._backend.get(self._namespaced(key))
        if raw is None:
            return default
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else config.CACHE_DEFAULT_TTL_SECONDS
        self._backend.set(self._namespaced(key), json.dumps(value), ttl)

    def delete(self, key: str) -> None:
        self._backend.delete(self._namespaced(key))

    def delete_prefix(self, prefix: str) -> int:
        """Bulk-invalidate every key starting with `prefix` (after namespacing)."""
        return self._backend.delete_prefix(self._namespaced(prefix))

    def clear(self) -> None:
        self._backend.clear()

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def cached(self, ttl_seconds: Optional[int] = None, key_prefix: Optional[str] = None):
        """
        Decorator: caches a function's return value, keyed on the
        function's qualified name plus a hash of its arguments.

        The wrapped value MUST be JSON-serializable (dicts, lists,
        strings, numbers, bools, None). If your function returns a
        dataclass or ORM object, convert it to a dict before
        returning, or cache around the call instead of decorating it
        directly.
        """

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

            # Attach for invalidate_function() to use — keeps the key
            # derivation in one place rather than duplicated at call sites.
            wrapper._synon_cache_prefix = prefix
            return wrapper

        return decorator

    def invalidate_function(self, decorated_func: Callable, *args, **kwargs) -> None:
        """
        Invalidate a specific cached call of a @cached-decorated
        function, e.g. after a write makes that specific cached
        result stale.

            @cache.cached(ttl_seconds=300)
            def get_user(user_id): ...

            # after updating user 42:
            cache.invalidate_function(get_user, user_id=42)
        """
        prefix = getattr(decorated_func, "_synon_cache_prefix", None)
        if prefix is None:
            raise ValueError(
                "invalidate_function() requires a function decorated with @cache.cached(...)"
            )
        cache_key = self._build_function_key(prefix, args, kwargs)
        self.delete(cache_key)

    def invalidate_all_for_function(self, decorated_func: Callable) -> int:
        """
        Invalidate EVERY cached call of a @cached-decorated function,
        regardless of arguments. Use when you don't know (or don't
        want to enumerate) which specific argument combinations are
        stale — e.g. "something about this product changed, blow away
        every cached variant of get_product_catalog".
        """
        prefix = getattr(decorated_func, "_synon_cache_prefix", None)
        if prefix is None:
            raise ValueError(
                "invalidate_all_for_function() requires a function decorated with @cache.cached(...)"
            )
        return self.delete_prefix(prefix)

    @staticmethod
    def _build_function_key(prefix: str, args: tuple, kwargs: dict) -> str:
        # Stable across calls with equivalent args: sort kwargs, hash
        # the combined representation rather than using it raw (raw
        # args could contain ':' or other characters that mess with
        # key namespacing, and could get arbitrarily long).
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return f"{prefix}:{digest}"


class _Missing:
    """Sentinel distinct from None, since None is a valid cached value."""

    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
