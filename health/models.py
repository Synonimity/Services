"""
synon_health.models
--------------------
Shared enums and response schemas for the health check module.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    """Status of a single health check."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

    @property
    def severity(self) -> int:
        """Higher = worse. Used to compute overall status via max()."""
        return {
            CheckStatus.HEALTHY: 0,
            CheckStatus.DEGRADED: 1,
            CheckStatus.UNHEALTHY: 2,
        }[self]

    @classmethod
    def worst_of(cls, statuses: list["CheckStatus"]) -> "CheckStatus":
        if not statuses:
            return cls.HEALTHY
        return max(statuses, key=lambda s: s.severity)


class CheckResult(BaseModel):
    """Result of a single named health check."""

    name: str
    status: CheckStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class LivenessResponse(BaseModel):
    """Response for GET /health — process-alive check only, no dependencies."""

    status: CheckStatus
    service: str
    uptime_seconds: float


class DeepHealthResponse(BaseModel):
    """Response for GET /health/deep — aggregates all registered checks."""

    status: CheckStatus
    service: str
    uptime_seconds: float
    checks: list[CheckResult]
