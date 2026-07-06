"""
synon_health.checks.cache_check
----------------------------------
Verifies a synon_cache backend (MemoryBackend or RedisBackend) is working
by doing a real set -> get -> delete round trip with a throwaway key.
Works with either backend since both implement the same
get/set/delete interface — this check never imports synon_cache directly,
it just calls whatever backend instance is passed in.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..models import CheckResult, CheckStatus

_PING_VALUE = "ok"


def make_cache_check(cache_backend: Any, degraded_above_ms: float = 100.0) -> Any:
    """
    Build a cache health check.

    Args:
        cache_backend: an instance of synon_cache's MemoryBackend or
            RedisBackend (anything exposing async set/get/delete).
        degraded_above_ms: latency threshold for DEGRADED vs HEALTHY.
    """

    async def check() -> CheckResult:
        key = f"synon_health:ping:{uuid.uuid4().hex[:8]}"
        start = time.monotonic()
        try:
            await cache_backend.set(key, _PING_VALUE, ttl=10)
            value = await cache_backend.get(key)
            await cache_backend.delete(key)
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="cache",
                status=CheckStatus.UNHEALTHY,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                message=f"{type(exc).__name__}: {exc}",
            )

        latency_ms = round((time.monotonic() - start) * 1000, 2)

        if value != _PING_VALUE:
            return CheckResult(
                name="cache",
                status=CheckStatus.UNHEALTHY,
                latency_ms=latency_ms,
                message="round-trip value mismatch (wrote but couldn't read back correctly)",
            )

        status = CheckStatus.DEGRADED if latency_ms > degraded_above_ms else CheckStatus.HEALTHY
        return CheckResult(
            name="cache",
            status=status,
            latency_ms=latency_ms,
            message=None if status == CheckStatus.HEALTHY else "slow response",
        )

    return check
