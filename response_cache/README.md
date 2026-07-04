# synon_response_cache

Deduplicates identical LLM calls so you don't pay tokens/latency twice for
the same request. Cache key is a deterministic hash (SHA-256) of model +
messages + system prompt + generation params — same inputs always
produce the same key, regardless of dict key ordering.

> Note: this is LLM-call-specific (key hashing, TTL, hit/miss stats). If
> you've already got `synon_cache` wired into a project as generic
> caching infra, you can point this module's `CacheBackend` interface at
> it instead of `InMemoryBackend`/`RedisBackend` — just write a thin
> adapter. Kept separate here so this module has zero opinion about your
> broader caching setup.

## Quick start — manual

```python
from response_cache import ResponseCache
from backends import InMemoryBackend

cache = ResponseCache(backend=InMemoryBackend(), ttl_seconds=3600)

hit = cache.get(model="claude-sonnet-5", messages=messages)
if hit is not None:
    return hit

reply = call_llm(messages)  # your llm_caller.py call
cache.set(model="claude-sonnet-5", messages=messages, response=reply)
```

## Quick start — wrapped

```python
reply = cache.cached_call(
    model="claude-sonnet-5",
    messages=messages,
    call_fn=lambda: call_llm(messages),
)
```

`cached_call` checks the cache, calls `call_fn()` only on a miss, stores
the result, and returns it either way. One line instead of the manual
get/call/set dance.

## Stats

```python
print(cache.stats.hits, cache.stats.misses, cache.stats.hit_rate)
```

Useful for a dashboard or just eyeballing whether caching is actually
paying for itself on a given workload.

## Backends

- `InMemoryBackend` — zero setup, single process, no proactive TTL sweep
  (expired entries are just skipped on read). Good for dev/tests.
- `RedisBackend` — the real answer for anything multi-instance. Requires
  `REDIS_URL` and the `redis` package.

## When NOT to cache

Only cache reasonably deterministic workloads. If you're running high
temperature or the call genuinely needs fresh output every time (creative
writing, anything intentionally non-idempotent), skip the cache for that
call, or set a very low `ttl_seconds` — don't cache it globally by
default and then fight the cache later.

## Notes

- `params` (temperature, max_tokens, etc.) are part of the key on
  purpose — the same messages with different generation settings are
  treated as different requests, since they can legitimately produce
  different output.
- Values are stored as JSON. If your LLM responses aren't JSON-serializable
  as-is (e.g. custom objects), serialize them yourself before calling
  `set()`/`cached_call()`.
