# synon_cache

Copy-in caching module: cache-aside pattern, TTL expiry, manual
invalidation hooks. Pluggable backend — works with zero infra
(in-process memory) by default, upgradeable to Redis when a product
actually needs shared/persistent caching.

**Convention:** importable Python package, not a standalone service.

## Why caching is the one place this library uses Redis, not Supabase

`synon_webhooks` and `synon_scheduler` both deliberately chose
Supabase over Redis — that state needs to survive a crash, and you're
already running Supabase everywhere. Caching is the opposite case:
it's meant to be disposable, and speed is the entire point. Postgres
adds real per-query overhead (network round-trip + transaction
machinery) that fights against what a cache is for. Redis is built
for exactly this — in-memory, sub-millisecond, TTL native to the
store. That's why this module defaults to an in-process dict (zero
infra at all) and treats Redis as the upgrade path, rather than
reaching for Supabase like the other two modules did.

## Picking a backend

- **`memory` (default)** — zero infra, nothing to provision. Good for
  single-process apps, dev, or a product that doesn't need caching
  shared across multiple workers/instances.
  **Limitation:** per-process. If you run multiple workers (e.g.
  several uvicorn workers, or multiple deployed instances), each one
  has its own separate cache — they don't share state, and the cache
  is wiped on every restart.
- **`redis`** — shared across workers/instances, survives your app
  restarting. Needed once a product scales past a single process, or
  if cached data needs to persist through deploys.

Switch via the `CACHE_BACKEND` env var. No code changes needed —
`Cache()` picks the backend based on config unless you pass one
explicitly.

## Setup

1. Copy this folder into your project.
2. Leave `.env` alone for the zero-infra memory backend, or set
   `CACHE_BACKEND=redis` and `REDIS_URL=...` if you want Redis.
3. If using Redis: `pip install redis` (only needed for that backend
   — the memory backend has zero dependencies).

## Explicit get/set/delete

```python
from synon_cache import Cache

cache = Cache()

cache.set("product:kerfcut:catalog", catalog_data, ttl_seconds=600)
catalog = cache.get("product:kerfcut:catalog")  # None if missing/expired
cache.delete("product:kerfcut:catalog")
```

## Decorator — caches a function's return value

This is the primary way you'll use this day-to-day: wrap a function
that does an expensive Supabase query (or anything else worth not
re-running), and repeated calls with the same arguments hit the
cache instead.

```python
@cache.cached(ttl_seconds=300)
def get_product_catalog(product_id: str):
    return supabase_query_that_is_too_slow_to_run_every_time(product_id)

get_product_catalog("kerfcut")  # runs the query, caches result
get_product_catalog("kerfcut")  # returns cached result, no query
get_product_catalog("kerfstock")  # different args = different cache entry, runs query
```

**The return value must be JSON-serializable** — dicts, lists,
strings, numbers, booleans, `None`. If your function returns a
dataclass, ORM row, or other object, convert it to a dict before
returning (or don't decorate it — cache around the call manually with
explicit `get`/`set` instead).

## Manual invalidation — for when a write makes a cached read stale

TTL alone isn't always enough — sometimes you know exactly when data
changed and want to invalidate immediately rather than waiting for
the TTL to expire.

```python
# Invalidate one specific cached call (same args as when it was cached)
cache.invalidate_function(get_product_catalog, "kerfcut")

# Invalidate EVERY cached call of this function, regardless of args —
# use when you don't know which specific arg combinations are stale
cache.invalidate_all_for_function(get_product_catalog)
```

Typical pattern: call this inside whatever handler processes the
write (a webhook handler, an API route that updates the underlying
data, etc.) right after the write succeeds.

## Bulk invalidation by key prefix

For cache keys you set manually (not via the decorator) but still
want to invalidate in bulk:

```python
cache.set("session:user42:cart", cart_data)
cache.set("session:user42:preferences", prefs_data)

cache.delete_prefix("session:user42:")  # clears both
```

## Namespacing across products

If multiple products end up sharing one Redis instance, set a
distinct `CACHE_KEY_PREFIX` per product (or pass `key_prefix=` to
`Cache()` directly) so their keys never collide:

```python
cache = Cache(key_prefix="kerfcut")
```

## Files

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings (ALL_CAPS_SNAKE) |
| `backends/base.py` | `CacheBackend` plug-in interface |
| `backends/memory.py` | Zero-infra in-process dict backend (default) |
| `backends/redis_backend.py` | Opt-in Redis backend |
| `cache.py` | `Cache` — the public API: get/set/delete, decorator, invalidation |

## Known untested piece

The Redis backend's method calls were tested structurally against a
mocked client (correct arguments, uses `scan_iter` not the blocking
`KEYS` command, etc.) but not against a real Redis server — none was
reachable in the build environment. Do a quick smoke test
(`cache.set`/`cache.get`/`cache.delete_prefix`) the first time you
point this at a real Redis instance.
