"""
example_integration.py
-----------------------
Not part of the module itself — a reference for wiring synon_health into
a host app that already has synon_cache and synon_ratelimit set up.
Delete or adapt this file; it won't be imported by anything.
"""

from fastapi import FastAPI

from synon_health.checks.cache_check import make_cache_check
from synon_health.checks.redis_check import make_redis_check
from synon_health.checks.supabase_check import make_supabase_check
from synon_health.registry import HealthCheckRegistry
from synon_health.router import build_health_router

# --- stand-ins for whatever your app already has ---------------------------
# supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
# cache_backend = RedisBackend(redis_url=...)  # from synon_cache
# ratelimit_redis_client = redis.asyncio.from_url(...)  # from synon_ratelimit
# -----------------------------------------------------------------------------

registry = HealthCheckRegistry(service_name="kerfportal-api")

# Wire in whatever this service actually depends on. Only register what's
# relevant — a service with no Redis usage just skips make_redis_check.
# registry.register("supabase", make_supabase_check(supabase_client))
# registry.register("cache", make_cache_check(cache_backend))
# registry.register(
#     "ratelimit_redis",
#     make_redis_check(ratelimit_redis_client, name="ratelimit_redis"),
# )

app = FastAPI()
app.include_router(build_health_router(registry))

# GET /health       -> {"status": "healthy", "service": "kerfportal-api", "uptime_seconds": 12.3}
# GET /health/deep  -> {"status": "healthy", "service": "...", "uptime_seconds": ..., "checks": [...]}
