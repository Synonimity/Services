"""
synon_scheduler.runner

Call `run_due_jobs()` from a scheduled tick (cron, systemd timer, or
a simple `while True: tick(); sleep(N)` script). This module does not
run its own loop — same convention as synon_webhooks.queue_processor.

A single tick does two things, in order:
  1. Advances due recurring jobs (enqueues a one-off ScheduledJob for
     each, then pushes their next_run_at forward)
  2. Claims and runs due one-off jobs (including the ones just
     enqueued by step 1)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import config
from .models import ScheduledJob
from .store import SchedulerStore

logger = logging.getLogger("synon_scheduler")

# A handler takes the claimed job and does the actual work. Raise any
# exception to signal failure -> triggers retry/backoff, same pattern
# as synon_webhooks handlers.
JobHandler = Callable[[ScheduledJob], None]


def compute_backoff_seconds(attempt_count: int) -> int:
    """Exponential backoff, identical shape to synon_webhooks."""
    backoff = config.JOB_BASE_BACKOFF_SECONDS * (2**attempt_count)
    return min(backoff, config.JOB_MAX_BACKOFF_SECONDS)


def tick_recurring_jobs(store: SchedulerStore) -> int:
    """
    Enqueues a ScheduledJob for every due RecurringJob, then advances
    each one's next_run_at. Returns the number enqueued.
    """
    due = store.get_due_recurring()
    for recurring in due:
        job = ScheduledJob(job_type=recurring.job_type, payload=recurring.payload)
        store.enqueue(job)
        store.advance_recurring(recurring)
        logger.info(
            "synon_scheduler: enqueued recurring job '%s' (next run in %ds)",
            recurring.job_type,
            recurring.interval_seconds,
        )
    return len(due)


def run_due_jobs(
    store: SchedulerStore,
    handlers: dict[str, JobHandler],
    limit: int = 20,
) -> dict[str, int]:
    """
    One full tick: advance recurring jobs, then claim and run due
    one-off jobs. Returns a summary dict for logging/monitoring.
    """
    enqueued_from_recurring = tick_recurring_jobs(store)

    summary = {
        "enqueued_from_recurring": enqueued_from_recurring,
        "claimed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
    }

    claimed_jobs = store.claim_due_jobs(limit=limit)
    summary["claimed"] = len(claimed_jobs)

    for job in claimed_jobs:
        handler = handlers.get(job.job_type)

        if handler is None:
            logger.warning(
                "synon_scheduler: no handler registered for job_type '%s', skipping job %s",
                job.job_type,
                job.id,
            )
            # Put it back as pending rather than leaving it stuck
            # "running" with no handler ever able to claim it again
            # before the stale-claim timeout.
            store.mark_failed(job, error="no handler registered", next_run_at=job.run_at)
            summary["skipped"] += 1
            continue

        try:
            handler(job)
            store.mark_succeeded(job)
            summary["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001 — job handlers are arbitrary, must not crash the loop
            backoff_seconds = compute_backoff_seconds(job.attempt_count)
            next_run_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

            logger.error(
                "synon_scheduler: handler failed for job %s (type=%s, attempt=%d): %s",
                job.id,
                job.job_type,
                job.attempt_count + 1,
                exc,
                exc_info=True,
            )

            store.mark_failed(job, error=str(exc), next_run_at=next_run_at)
            summary["failed"] += 1

    return summary
