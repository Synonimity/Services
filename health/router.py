"""
synon_health.router
---------------------
Drop-in FastAPI router. Wire it up in your app with:

    from fastapi import FastAPI
    from synon_health.router import build_health_router
    from synon_health.registry import HealthCheckRegistry
    from synon_health.checks.supabase_check import make_supabase_check
    from synon_health.checks.cache_check import make_cache_check
    from synon_health.checks.redis_check import make_redis_check

    registry = HealthCheckRegistry(service_name="kerfportal-api")
    registry.register("supabase", make_supabase_check(supabase_client))
    registry.register("cache", make_cache_check(cache_backend))
    registry.register("ratelimit_redis", make_redis_check(ratelimit_redis_client, name="ratelimit_redis"))

    app = FastAPI()
    app.include_router(build_health_router(registry))

GET /health       -> liveness only. Always fast, always 200 if the process
                     is up. Point your uptime monitor / load balancer's
                     basic health probe here.
GET /health/deep  -> readiness. Runs every registered check concurrently.
                     Point this at anything that needs to know whether
                     dependencies (Supabase, Redis, etc.) are actually
                     reachable — e.g. a deploy gate or a status page.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from .config import CONFIG
from .models import CheckStatus, DeepHealthResponse, LivenessResponse
from .registry import HealthCheckRegistry, default_registry


def build_health_router(registry: HealthCheckRegistry | None = None) -> APIRouter:
    reg = registry or default_registry
    router = APIRouter(tags=["health"])

    @router.get("/health", response_model=LivenessResponse)
    async def liveness() -> LivenessResponse:
        return LivenessResponse(
            status=CheckStatus.HEALTHY,
            service=reg.service_name,
            uptime_seconds=round(reg.uptime_seconds, 2),
        )

    @router.get("/health/deep", response_model=DeepHealthResponse)
    async def deep_health(response: Response) -> DeepHealthResponse:
        result = await reg.run_all()

        if result.status == CheckStatus.UNHEALTHY:
            response.status_code = 503
        elif result.status == CheckStatus.DEGRADED and CONFIG.DEGRADED_RETURNS_503:
            response.status_code = 503
        # else: leave default 200

        return result

    return router
