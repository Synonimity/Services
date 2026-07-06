"""
synon_health.registry
----------------------
Central registry that other synon_* modules (or the host app) plug into.

Usage:
    from synon_health.registry import HealthCheckRegistry
    from synon_health.checks.supabase_check import make_supabase_check
    from synon_health.checks.cache_check import make_cache_check

    registry = HealthCheckRegistry(service_name="kerfportal-api")
    registry.register("supabase", make_supabase_check(supabase_client))
    registry.register("cache", make_cache_check(cache_backend))

Each check is an async callable: `async def check() -> CheckResult`.
A factory function (e.g. make_supabase_check) closes over whatever client
or backend it needs, so synon_health never imports synon_cache/synon_ratelimit
directly — it stays a dependency-free copy-in module.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from .config import CONFIG
from .models import CheckResult, CheckStatus, DeepHealthResponse

CheckFunc = Callable[[], Awaitable[CheckResult]]


class HealthCheckRegistry:
    def __init__(self, service_name: str | None = None) -> None:
        self.service_name = service_name or CONFIG.SERVICE_NAME
        self._checks: dict[str, CheckFunc] = {}
        self._start_time = time.monotonic()

        # Simple in-memory cache of the last deep-check result, to avoid
        # hammering backends if /health/deep is polled aggressively.
        self._cached_response: DeepHealthResponse | None = None
        self._cached_at: float = 0.0

    def register(self, name: str, check_func: CheckFunc) -> None:
        """Register a named async check. Overwrites any existing check of the same name."""
        if name in self._checks:
            # Not fatal — just means a re-register (e.g. hot reload in dev).
            pass
        self._checks[name] = check_func

    def unregister(self, name: str) -> None:
        self._checks.pop(name, None)

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    async def _run_one(self, name: str, check_func: CheckFunc) -> CheckResult:
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                check_func(), timeout=CONFIG.CHECK_TIMEOUT_SECONDS
            )
            # Fill in latency if the check didn't measure its own.
            if result.latency_ms is None:
                result.latency_ms = round((time.monotonic() - start) * 1000, 2)
            return result
        except asyncio.TimeoutError:
            return CheckResult(
                name=name,
                status=CheckStatus.UNHEALTHY,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                message=f"check timed out after {CONFIG.CHECK_TIMEOUT_SECONDS}s",
            )
        except Exception as exc:  # noqa: BLE001 — a failing check must not crash /health/deep
            return CheckResult(
                name=name,
                status=CheckStatus.UNHEALTHY,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                message=f"{type(exc).__name__}: {exc}",
            )

    async def run_all(self, use_cache: bool = True) -> DeepHealthResponse:
        """Run every registered check concurrently and aggregate the result."""
        now = time.monotonic()
        if (
            use_cache
            and CONFIG.DEEP_CHECK_CACHE_SECONDS > 0
            and self._cached_response is not None
            and (now - self._cached_at) < CONFIG.DEEP_CHECK_CACHE_SECONDS
        ):
            return self._cached_response

        results = await asyncio.gather(
            *(self._run_one(name, fn) for name, fn in self._checks.items())
        )
        overall = CheckStatus.worst_of([r.status for r in results])

        response = DeepHealthResponse(
            status=overall,
            service=self.service_name,
            uptime_seconds=round(self.uptime_seconds, 2),
            checks=list(results),
        )
        self._cached_response = response
        self._cached_at = now
        return response


# A default module-level registry so simple single-service setups can just
# `from synon_health.registry import default_registry` without wiring their
# own instance. Multi-service hosts should create their own HealthCheckRegistry.
default_registry = HealthCheckRegistry()
