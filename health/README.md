# synon_health

Copy-in health check module for the SynonTech template library. Tier 2, #1.

Two endpoints, one registry, zero required dependencies beyond FastAPI + pydantic.

## Why it's split this way

- **`GET /health`** — liveness. Proves the process is up and the event loop
  is responsive. No dependency checks, no timeouts to worry about, always
  fast. This is what your uptime monitor or the LB's basic probe should hit
  every few seconds.
- **`GET /health/deep`** — readiness. Runs every registered check
  concurrently (Supabase, cache backend, Redis, whatever you've wired in)
  and returns an aggregated status. Point this at a deploy gate, an
  internal status page, or a less-frequent monitor — not at a tight
  polling loop, since it touches real dependencies.

Mixing these into one endpoint is the usual mistake: an LB doing 1
liveness check/sec shouldn't also be hammering your Postgres connection
that often.

## Install

Drop the `synon_health/` folder into your project. No Supabase table, no
migration, no `schema.sql` — this module holds no state of its own beyond
an in-process start time and a short-lived result cache.

```
pip install -r synon_health/requirements.txt
```

`supabase` and `redis` are commented out in requirements.txt — only
uncomment/install whichever checks you actually wire up. `synon_health`
never imports them directly (see "How checks work" below).

## Quick start

```python
from fastapi import FastAPI
from synon_health.registry import HealthCheckRegistry
from synon_health.router import build_health_router
from synon_health.checks.supabase_check import make_supabase_check
from synon_health.checks.cache_check import make_cache_check
from synon_health.checks.redis_check import make_redis_check

registry = HealthCheckRegistry(service_name="kerfportal-api")
registry.register("supabase", make_supabase_check(supabase_client))
registry.register("cache", make_cache_check(cache_backend))          # synon_cache
registry.register("ratelimit_redis", make_redis_check(ratelimit_redis_client))  # synon_ratelimit

app = FastAPI()
app.include_router(build_health_router(registry))
```

See `example_integration.py` for a fuller reference.

## How checks work

Every check is `async def check() -> CheckResult`. The `checks/` folder
ships factory functions that build these closures around whatever
client/backend you pass in:

| Factory | Wraps | Notes |
|---|---|---|
| `self_check` | nothing | always healthy, proves the loop runs |
| `make_supabase_check(client, table=...)` | supabase-py client | runs a `select().limit(1)` in a thread executor (client is sync) |
| `make_cache_check(backend)` | synon_cache `MemoryBackend`/`RedisBackend` | real set→get→delete round trip |
| `make_redis_check(client_or_backend, name=...)` | raw redis.asyncio client or any backend wrapping one | plain `PING`; use `name=` to register more than one (e.g. `"cache_redis"` + `"ratelimit_redis"`) |

`synon_health` itself never imports `supabase`, `redis`, or any other
`synon_*` module — the factories just call methods on whatever object you
hand them. Register your own check the same way for anything not covered
here (an external API, a queue, a licensing pool, etc.):

```python
async def my_check() -> CheckResult:
    ...
    return CheckResult(name="stripe", status=CheckStatus.HEALTHY)

registry.register("stripe", my_check)
```

## Status semantics

- **HEALTHY** — check passed, latency under threshold.
- **DEGRADED** — check passed but was slow (thresholds are per-check
  kwargs, e.g. `degraded_above_ms=300` for Supabase).
- **UNHEALTHY** — check failed, threw, or timed out.

Overall status on `/health/deep` is the worst of all individual checks.

HTTP status codes:
- `UNHEALTHY` overall → always `503`.
- `DEGRADED` overall → `200` by default, or `503` if
  `HEALTH_DEGRADED_RETURNS_503=true` (strict mode — pulls the instance out
  of LB rotation on any slowness, not just outright failure).
- `HEALTHY` overall → `200`.

## Config (all optional, see `.env.example`)

| Var | Default | Purpose |
|---|---|---|
| `HEALTH_SERVICE_NAME` | `synon-service` | shown in responses |
| `HEALTH_CHECK_TIMEOUT_SECONDS` | `5.0` | per-check timeout before forced `UNHEALTHY` |
| `HEALTH_DEGRADED_RETURNS_503` | `false` | strict vs lenient degraded handling |
| `HEALTH_DEEP_CHECK_CACHE_SECONDS` | `2.0` | throttles repeated `/health/deep` hits; `0` disables |

## What this deliberately doesn't do (v1)

No persistent history/incident log in Supabase — this is meant to be the
"set it and forget it forever" module, not another thing to maintain.
If you later want a `synon_health_history` table logging every
DEGRADED/UNHEALTHY transition (useful for an uptime dashboard or for
catching the kind of gap the Linker.AI audit trail work is fixing on the
content side), that's a clean Tier 2.5 add-on — a `HealthCheckRegistry`
subclass or a post-check hook — not a v1 requirement.
