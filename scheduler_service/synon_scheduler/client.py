"""
synon_scheduler.client

Convenience functions for the calling side — your app code that
wants to enqueue a job, as opposed to the worker side (runner.py)
that executes them.

    from synon_scheduler import SchedulerStore
    from synon_scheduler.client import enqueue_job, register_recurring

    store = SchedulerStore()
    enqueue_job(store, "send_email", {"to": "...", "template": "..."})
    register_recurring(store, "webhook_tick", interval_seconds=30)
"""

from datetime import datetime, timezone
from typing import Any, Optional

from .models import RecurringJob, ScheduledJob
from .store import SchedulerStore


def enqueue_job(
    store: SchedulerStore,
    job_type: str,
    payload: Optional[dict[str, Any]] = None,
    run_at: Optional[datetime] = None,
    max_retries: int = 5,
) -> ScheduledJob:
    """
    Queue a one-off job. Defaults to running ASAP (next worker tick).
    Pass `run_at` for a delayed job, e.g. "send reminder in 24 hours".
    """
    job = ScheduledJob(
        job_type=job_type,
        payload=payload or {},
        run_at=run_at or datetime.now(timezone.utc),
        max_retries=max_retries,
    )
    return store.enqueue(job)


def register_recurring(
    store: SchedulerStore,
    job_type: str,
    interval_seconds: int,
    payload: Optional[dict[str, Any]] = None,
    enabled: bool = True,
) -> RecurringJob:
    """
    Register (or update, if job_type already exists) a recurring job.
    Safe to call on every app startup — it upserts rather than
    duplicating.
    """
    recurring = RecurringJob(
        job_type=job_type,
        interval_seconds=interval_seconds,
        payload=payload or {},
        enabled=enabled,
    )
    return store.register_recurring(recurring)
