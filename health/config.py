"""
synon_health.config
--------------------
Env-driven configuration. Sensible defaults so this works with zero setup
in dev, and can be tightened in prod via env vars.
"""

from __future__ import annotations

import os


def _get_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _get_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


class HealthConfig:
    """Loaded once at import time. Override via env vars before import if needed."""

    SERVICE_NAME: str = os.getenv("HEALTH_SERVICE_NAME", "synon-service")

    # Per-check timeout. A hung dependency should never hang the whole endpoint.
    CHECK_TIMEOUT_SECONDS: float = _get_float("HEALTH_CHECK_TIMEOUT_SECONDS", 5.0)

    # Whether a DEGRADED overall status should cause /health/deep to return
    # HTTP 503 (strict, good for load balancer eviction) or 200 (lenient,
    # good if you don't want a slow dependency to pull the instance out of
    # rotation). UNHEALTHY always returns 503 regardless of this setting.
    DEGRADED_RETURNS_503: bool = _get_bool("HEALTH_DEGRADED_RETURNS_503", False)

    # Cache the deep-check result for this many seconds to avoid hammering
    # Supabase/Redis if something (e.g. an LB) polls /health/deep aggressively.
    # Set to 0 to disable caching entirely.
    DEEP_CHECK_CACHE_SECONDS: float = _get_float("HEALTH_DEEP_CHECK_CACHE_SECONDS", 2.0)


CONFIG = HealthConfig()
