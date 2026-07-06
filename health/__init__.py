"""
synon_health
------------
Copy-in health check module for the SynonTech template library.

Public API:
    HealthCheckRegistry   -- register named async checks, run them, aggregate
    build_health_router   -- FastAPI router with /health and /health/deep
    CheckResult, CheckStatus -- shared models

    make_supabase_check   -- checks/supabase_check.py
    make_cache_check      -- checks/cache_check.py
    make_redis_check      -- checks/redis_check.py
    self_check            -- checks/builtin.py, registered as "self" if desired

See README.md for wiring instructions.
"""

from .checks.builtin import self_check
from .checks.cache_check import make_cache_check
from .checks.redis_check import make_redis_check
from .checks.supabase_check import make_supabase_check
from .models import CheckResult, CheckStatus, DeepHealthResponse, LivenessResponse
from .registry import HealthCheckRegistry, default_registry
from .router import build_health_router

__all__ = [
    "HealthCheckRegistry",
    "default_registry",
    "build_health_router",
    "CheckResult",
    "CheckStatus",
    "DeepHealthResponse",
    "LivenessResponse",
    "self_check",
    "make_supabase_check",
    "make_cache_check",
    "make_redis_check",
]
