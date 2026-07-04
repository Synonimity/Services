"""
synon_scheduler.store

Supabase-backed persistence for jobs. The important bit here is
`claim_due_jobs()` — it must be atomic, otherwise two overlapping
worker ticks (e.g. a slow tick still running when the next cron fire
happens) could both grab the same job and run it twice.

We do this with an UPDATE ... WHERE status = 'pending' RETURNING,
via a Postgres function (see schema.sql: claim_jobs()), rather than a
SELECT then UPDATE. SELECT-then-UPDATE has a race window between the
two calls; a single atomic UPDATE does not.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client, create_client

from . import config
from .models import JobStatus, RecurringJob, ScheduledJob


class SchedulerStore:
    def __init__(self, client: Optional[Client] = None):
        if client is not None:
            self._client = client
        else:
            config.validate_config()
            self._client = create_client(
                config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY
            )
        self._jobs_table = config.JOBS_TABLE
        self._recurring_table = config.RECURRING_JOBS_TABLE

    # ------------------------------------------------------------------
    # One-off jobs
    # ------------------------------------------------------------------

    def enqueue(self, job: ScheduledJob) -> ScheduledJob:
        result = self._client.table(self._jobs_table).insert(job.to_row()).execute()
        row = result.data[0]
        job.id = row["id"]
        return job

    def claim_due_jobs(self, limit: int = 20) -> list[ScheduledJob]:
        """
        Atomically claims up to `limit` due jobs by calling the
        `claim_jobs` Postgres function (see schema.sql). This avoids
        the race condition of SELECT-then-UPDATE across overlapping
        worker ticks.
        """
        now = datetime.now(timezone.utc)
        claim_stale_cutoff = now - timedelta(minutes=config.JOB_CLAIM_TIMEOUT_MINUTES)

        result = self._client.rpc(
            "claim_jobs",
            {
                "p_table": self._jobs_table,
                "p_limit": limit,
                "p_now": now.isoformat(),
                "p_stale_cutoff": claim_stale_cutoff.isoformat(),
            },
        ).execute()

        return [ScheduledJob.from_row(row) for row in result.data]

    def mark_succeeded(self, job: ScheduledJob) -> None:
        job.status = JobStatus.SUCCEEDED
        job.completed_at = datetime.now(timezone.utc)
        self._update_job(job)

    def mark_failed(self, job: ScheduledJob, error: str, next_run_at: Optional[datetime]) -> None:
        job.attempt_count += 1
        job.last_error = error[:2000]
        job.claimed_at = None

        if next_run_at is not None and job.attempt_count < job.max_retries:
            job.status = JobStatus.PENDING
            job.run_at = next_run_at
        else:
            job.status = JobStatus.DEAD_LETTERED

        self._update_job(job)

    def get_dead_lettered(self, limit: int = 50) -> list[ScheduledJob]:
        result = (
            self._client.table(self._jobs_table)
            .select("*")
            .eq("status", JobStatus.DEAD_LETTERED.value)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [ScheduledJob.from_row(row) for row in result.data]

    def _update_job(self, job: ScheduledJob) -> None:
        self._client.table(self._jobs_table).update(job.to_row()).eq("id", job.id).execute()

    # ------------------------------------------------------------------
    # Recurring jobs
    # ------------------------------------------------------------------

    def register_recurring(self, recurring: RecurringJob) -> RecurringJob:
        """
        Upsert by job_type — registering the same recurring job twice
        (e.g. on every app startup) updates the definition rather than
        creating duplicates.
        """
        result = (
            self._client.table(self._recurring_table)
            .upsert(recurring.to_row(), on_conflict="job_type")
            .execute()
        )
        row = result.data[0]
        recurring.id = row["id"]
        return recurring

    def get_due_recurring(self) -> list[RecurringJob]:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            self._client.table(self._recurring_table)
            .select("*")
            .eq("enabled", True)
            .lte("next_run_at", now)
            .execute()
        )
        return [RecurringJob.from_row(row) for row in result.data]

    def advance_recurring(self, recurring: RecurringJob) -> None:
        """Push next_run_at forward by interval_seconds, record last_run_at."""
        now = datetime.now(timezone.utc)
        recurring.last_run_at = now
        recurring.next_run_at = now + timedelta(seconds=recurring.interval_seconds)
        self._client.table(self._recurring_table).update(
            recurring.to_row()
        ).eq("id", recurring.id).execute()
