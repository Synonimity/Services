"""
synon_health.checks.redis_check
----------------------------------
Verifies a Redis connection is alive via PING. Generic — use this for
synon_ratelimit's RedisBackend, synon_cache's RedisBackend, or any raw
redis.asyncio client, since all of them wrap (or are) a real Redis
connection somewhere.

Resolution order for finding something to ping:
  1. object itself has an async `.ping()` (raw redis-py client)
  2. object exposes `.redis` or `._redis` attribute with `.ping()`
     (common pattern for our backend wrapper classes)
"""

from __future__ import annotations

import time
from typing import Any

from ..models import CheckResult, CheckStatus


def _resolve_pingable(obj: Any) -> Any:
    if hasattr(obj, "ping"):
        return obj
    for attr in ("redis", "_redis", "client", "_client"):
        inner = getattr(obj, attr, None)
        if inner is not None and hasattr(inner, "ping"):
            return inner
    raise AttributeError(
        "could not find a pingable redis client — pass the raw redis client, "
        "or one whose backend exposes it as .redis/.client"
    )


def make_redis_check(
    redis_or_backend: Any,
    name: str = "redis",
    degraded_above_ms: float = 50.0,
) -> Any:
    """
    Build a Redis health check.

    Args:
        redis_or_backend: a redis.asyncio client, or a synon_* RedisBackend
            instance wrapping one.
        name: check name — pass e.g. "ratelimit_redis" or "cache_redis" if
            registering more than one Redis-backed check, so they're
            distinguishable in the /health/deep response.
        degraded_above_ms: latency threshold for DEGRADED vs HEALTHY.
    """
    try:
        client = _resolve_pingable(redis_or_backend)
    except AttributeError as exc:
        # Fail loudly at registration time rather than silently at request time —
        # a misconfigured check is a setup bug, not a runtime health event.
        raise ValueError(f"make_redis_check: {exc}") from exc

    async def check() -> CheckResult:
        start = time.monotonic()
        try:
            await client.ping()
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name=name,
                status=CheckStatus.UNHEALTHY,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                message=f"{type(exc).__name__}: {exc}",
            )

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        status = CheckStatus.DEGRADED if latency_ms > degraded_above_ms else CheckStatus.HEALTHY
        return CheckResult(
            name=name,
            status=status,
            latency_ms=latency_ms,
            message=None if status == CheckStatus.HEALTHY else "slow response",
        )

    return check
