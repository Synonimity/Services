"""
synon_health.checks.supabase_check
------------------------------------
Verifies Supabase (Postgres via PostgREST) is reachable using the same
service_role/adminClient the host app already uses elsewhere in the
synon_* template library — this module never creates its own client.

The supabase-py client is synchronous, so the query runs in a thread
executor to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..models import CheckResult, CheckStatus


def make_supabase_check(
    supabase_client: Any,
    table: str = "synon_health_ping",
    degraded_above_ms: float = 300.0,
) -> Any:
    """
    Build a Supabase health check.

    Args:
        supabase_client: an initialised supabase-py Client (service_role/adminClient).
        table: any small table the service_role key can SELECT from with limit 1.
            Doesn't need to be meaningful data — a 1-row query is enough to prove
            the DB round-trip works. Defaults to a convention table name; point
            it at any existing table (e.g. "synon_licensing_pool") if you'd
            rather not create a dedicated one.
        degraded_above_ms: latency threshold above which status is DEGRADED
            rather than HEALTHY, even though the query succeeded.
    """

    def _run_query() -> None:
        supabase_client.table(table).select("*").limit(1).execute()

    async def check() -> CheckResult:
        start = time.monotonic()
        try:
            await asyncio.get_event_loop().run_in_executor(None, _run_query)
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="supabase",
                status=CheckStatus.UNHEALTHY,
                latency_ms=round((time.monotonic() - start) * 1000, 2),
                message=f"{type(exc).__name__}: {exc}",
            )

        latency_ms = round((time.monotonic() - start) * 1000, 2)
        status = CheckStatus.DEGRADED if latency_ms > degraded_above_ms else CheckStatus.HEALTHY
        return CheckResult(
            name="supabase",
            status=status,
            latency_ms=latency_ms,
            message=None if status == CheckStatus.HEALTHY else "slow response",
        )

    return check
