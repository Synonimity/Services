# synon_ratelimit

Copy-in rate limiting module using a token bucket algorithm. Pairs
naturally with `synon_auth` (per-user limits) and `synon_licensing`
(stop someone hammering `validate_license` with guessed keys).
Pluggable backend, same pattern as `synon_cache`.

**Convention:** importable Python package, not a standalone service.

## Why token bucket, not fixed window

Fixed window ("100 requests per minute") has a real edge-case flaw:
someone can send 100 requests at 0:59 and another 100 at 1:01,
getting 200 requests in 2 seconds while technically staying within
each window's limit. Token bucket has no window boundary to exploit
— it tracks a continuously-refilling allowance instead, so there's no
seam to burst across. It's barely more complex to implement, so
there's no real cost to picking the better algorithm.

## Picking a backend

Same tradeoff as `synon_cache`:

- **`memory` (default)** — zero infra. **Limitation: per-process.**
  If you run multiple workers, the limit is enforced separately by
  EACH worker — "10 req/min" becomes "10 req/min per worker," not
  "10 req/min total." Fine for a single-process app or dev.
- **`redis`** — limit enforced globally across all workers/instances.
  Needed once a product scales past a single process, or you're
  protecting a shared downstream resource (e.g. a paid third-party
  API with its own rate limit you need to respect across all your
  workers combined).

The Redis backend uses a Lua script so the check-and-consume
operation is atomic on the Redis server — without that, two
simultaneous requests could both read the bucket as "not empty"
before either writes back the decremented value, letting more
through than the limit allows. Same race-condition concern as
`synon_scheduler`'s `claim_jobs()` and `synon_licensing`'s
`claim_pool_key()`, solved with Redis's equivalent mechanism instead
of a SQL atomic UPDATE.

## Setup

1. Copy this folder into your project.
2. Leave `.env` alone for the zero-infra memory backend, or set
   `RATELIMIT_BACKEND=redis` and `REDIS_URL=...`.
3. If using Redis: `pip install redis`.

## Explicit check

```python
from synon_ratelimit import RateLimiter

limiter = RateLimiter()

result = limiter.check("user:42", capacity=10, window_seconds=60)
if not result.allowed:
    print(f"Rate limited. Try again in {result.retry_after_seconds:.0f}s")
else:
    # proceed — result.tokens_remaining tells you how much headroom is left
    ...
```

## Decorator

`key_func` receives the same arguments the wrapped function is
called with, and returns a string identifying who/what to limit —
you decide which argument that is (a user ID, an IP, a license key,
whatever the function has access to).

```python
from synon_ratelimit import RateLimiter, RateLimitExceeded

limiter = RateLimiter()

@limiter.limit(key_func=lambda request: f"ip:{request.client.host}", capacity=20, window_seconds=60)
def handle_login(request):
    ...
```

In FastAPI, catch `RateLimitExceeded` in an exception handler to
return a proper 429 with a `Retry-After` header:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from synon_ratelimit import RateLimitExceeded

app = FastAPI()

@app.exception_handler(RateLimitExceeded)
def handle_rate_limit(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests"},
        headers={"Retry-After": str(int(exc.result.retry_after_seconds) + 1)},
    )
```

## Weighting expensive operations

Use `cost` to make some calls drain the bucket faster than others —
e.g. a CDKey generation costs more "budget" than a simple status
check:

```python
limiter.check("user:42", capacity=100, window_seconds=60, cost=10)
```

## Protecting synon_licensing's validate_license

A direct, concrete use case for this library:

```python
from synon_licensing import validate_license
from synon_ratelimit import RateLimiter, RateLimitExceeded

limiter = RateLimiter()

def validate_license_rate_limited(store, key, product, **kwargs):
    # rate-limit by the KEY being attempted, not by IP — this stops
    # someone brute-forcing key guesses regardless of how many IPs
    # they spread the attempts across
    result = limiter.check(f"license_attempt:{key}", capacity=5, window_seconds=300)
    if not result.allowed:
        raise RateLimitExceeded(result)
    return validate_license(store, key, product, **kwargs)
```

## Files

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings (ALL_CAPS_SNAKE) |
| `backends/base.py` | `RateLimitBackend` plug-in interface |
| `backends/memory.py` | Zero-infra in-process token bucket (default) |
| `backends/redis_backend.py` | Opt-in Redis backend, atomic via Lua script |
| `limiter.py` | `RateLimiter` — the public API: check, decorator, reset |

## Known untested piece

The Redis backend's Lua script logic (the actual EVAL script string
in `redis_backend.py`) has been verified structurally — correct
script registration, correct arguments passed, correct result
parsing — against a mocked client, but the script's internal Lua
logic has NOT been executed against a real Redis server, since none
was reachable in the build environment. This is the single highest-
priority piece to verify before relying on the Redis backend in
production: register the script against a real Redis instance and
run the same concurrent-load test this module's memory backend
passed (many threads hammering one key, confirming the allowed count
exactly matches capacity, not more).
