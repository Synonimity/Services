"""
synon_response_cache
----------------------
Deduplicates identical LLM calls so you don't pay tokens/latency twice
for the same request. Cache key is a deterministic hash of everything
that affects the output: model, messages, system prompt, and any
generation params (temperature, max_tokens, etc.) you pass in.

Two ways to use it:

1. Manual get/set - check before calling, store after:

    cache = ResponseCache(backend=InMemoryBackend(), ttl_seconds=3600)

    hit = cache.get(model="claude-sonnet-5", messages=messages)
    if hit is not None:
        return hit
    reply = call_llm(...)
    cache.set(model="claude-sonnet-5", messages=messages, response=reply)

2. Wrapped call - pass the actual call function in, cache handles the
   check/store around it:

    reply = cache.cached_call(
        model="claude-sonnet-5", messages=messages,
        call_fn=lambda: call_llm(messages),
    )

Only cache deterministic-ish workloads. If temperature is high or the
call needs fresh output every time (creative writing, anything
non-idempotent), don't cache it - or set ttl_seconds very low / cache
selectively per-call.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Optional, Callable, Any, List, Dict

DEFAULT_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0


def _make_key(model: str, messages: List[Dict], system: Optional[str] = None, **params) -> str:
    """
    Deterministic key: same inputs -> same key, regardless of dict key
    ordering. sort_keys=True on json.dumps handles that.
    """
    payload = {
        "model": model,
        "messages": messages,
        "system": system,
        "params": params,
    }
    serialized = json.dumps(payload, sort_keys=True, default=str)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"llmcache:{digest}"


class ResponseCache:
    def __init__(self, backend, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.backend = backend
        self.ttl_seconds = ttl_seconds
        self.stats = CacheStats()

    def get(self, model: str, messages: List[Dict], system: Optional[str] = None, **params) -> Optional[str]:
        key = _make_key(model, messages, system, **params)
        cached = self.backend.get(key)
        if cached is not None:
            self.stats.hits += 1
            try:
                return json.loads(cached)["response"]
            except (json.JSONDecodeError, KeyError):
                return None
        self.stats.misses += 1
        return None

    def set(
        self,
        model: str,
        messages: List[Dict],
        response: Any,
        system: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        **params,
    ) -> None:
        key = _make_key(model, messages, system, **params)
        value = json.dumps({"response": response})
        self.backend.set(key, value, ttl_seconds or self.ttl_seconds)

    def invalidate(self, model: str, messages: List[Dict], system: Optional[str] = None, **params) -> None:
        key = _make_key(model, messages, system, **params)
        self.backend.delete(key)

    def cached_call(
        self,
        model: str,
        messages: List[Dict],
        call_fn: Callable[[], Any],
        system: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        **params,
    ) -> Any:
        """Check cache; on miss, call call_fn(), store the result, return it either way."""
        hit = self.get(model, messages, system, **params)
        if hit is not None:
            return hit

        result = call_fn()
        self.set(model, messages, result, system=system, ttl_seconds=ttl_seconds, **params)
        return result
