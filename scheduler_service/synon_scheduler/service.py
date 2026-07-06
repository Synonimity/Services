import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Callable, Optional

from .config import SchedulerConfig
from .models import ScheduledJob, RecurringJob
from .store import SchedulerStore

logger = logging.getLogger("synon_scheduler")

JobHandler = Callable[[ScheduledJob], None]


class SchedulerService:
    def __init__(self, config: SchedulerConfig, store: Optional[SchedulerStore] = None):
        self.config = config
        self.store = store or SchedulerStore(config=config)

    def enqueue(self, job_type: str, payload: Dict = None) -> ScheduledJob:
        job = ScheduledJob(job_type=job_type, payload=payload or {})
        return self.store.enqueue(job)

    def register_recurring(self, job_type: str, interval_seconds: int, payload: Dict = None) -> RecurringJob:
        recurring = RecurringJob(
            job_type=job_type,
            interval_seconds=interval_seconds,
            payload=payload or {}
        )
        return self.store.register_recurring(recurring)

    def run_due_jobs(self, handlers: Dict[str, JobHandler], limit: int = 20) -> Dict[str, int]:
        """One full tick: advance recurring, then claim and run one-off."""
        enqueued_from_recurring = self._tick_recurring_jobs()

        summary = {
            "enqueued_from_recurring": enqueued_from_recurring,
            "claimed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
        }

        claimed_jobs = self.store.claim_due_jobs(limit=limit)
        summary["claimed"] = len(claimed_jobs)

        for job in claimed_jobs:
            handler = handlers.get(job.job_type)

            if handler is None:
                logger.warning("synon_scheduler: no handler for '%s', skipping %s", job.job_type, job.id)
                self.store.mark_failed(job, error="no handler registered", next_run_at=job.run_at)
                summary["skipped"] += 1
                continue

            try:
                handler(job)
                self.store.mark_succeeded(job)
                summary["succeeded"] += 1
            except Exception as exc:
                backoff = self._compute_backoff(job.attempt_count)
                next_run = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                
                logger.error("synon_scheduler: job %s failed: %s", job.id, exc, exc_info=True)
                self.store.mark_failed(job, error=str(exc), next_run_at=next_run)
                summary["failed"] += 1

        return summary

    def _tick_recurring_jobs(self) -> int:
        due = self.store.get_due_recurring()
        for recurring in due:
            job = ScheduledJob(job_type=recurring.job_type, payload=recurring.payload)
            self.store.enqueue(job)
            self.store.advance_recurring(recurring)
        return len(due)

    def _compute_backoff(self, attempt_count: int) -> int:
        backoff = self.config.job_base_backoff_seconds * (2**attempt_count)
        return min(backoff, self.config.job_max_backoff_seconds)
