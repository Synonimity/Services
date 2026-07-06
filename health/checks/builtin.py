"""
synon_health.checks.builtin
-----------------------------
The "self" check — confirms the process is alive and the event loop is
responsive. No external dependencies. This is what backs GET /health
(liveness); it's cheap enough to poll every few seconds from an LB.
"""

from __future__ import annotations

from ..models import CheckResult, CheckStatus


async def self_check() -> CheckResult:
    """Always healthy if this coroutine ran at all — proves the loop is alive."""
    return CheckResult(name="self", status=CheckStatus.HEALTHY, message="process alive")
