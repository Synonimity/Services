"""
synon_scheduler.models

PascalCase data classes representing job state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


@dataclass
class ScheduledJob:
    """
    A single one-off job: run once, at or after `run_at`, with
    retry/backoff on failure. This is the same shape as a webhook
    event going through a retry queue — enqueue, claim, run, succeed
    or back off.
    """

    job_type: str  # e.g. "send_email", "generate_cdkey", "webhook_tick"
    payload: dict[str, Any] = field(default_factory=dict)
    status: JobStatus = JobStatus.PENDING
    run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 0
    max_retries: int = 5
    last_error: Optional[str] = None
    claimed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    id: Optional[str] = None  # set once persisted (Supabase row id)

    def to_row(self) -> dict[str, Any]:
        return {
            "job_type": self.job_type,
            "payload": self.payload,
            "status": self.status.value,
            "run_at": self.run_at.isoformat(),
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ScheduledJob":
        return cls(
            id=row.get("id"),
            job_type=row["job_type"],
            payload=row.get("payload") or {},
            status=JobStatus(row["status"]),
            run_at=_parse_dt(row.get("run_at")) or datetime.now(timezone.utc),
            attempt_count=row.get("attempt_count", 0),
            max_retries=row.get("max_retries", 5),
            last_error=row.get("last_error"),
            claimed_at=_parse_dt(row.get("claimed_at")),
            created_at=_parse_dt(row.get("created_at")) or datetime.now(timezone.utc),
            completed_at=_parse_dt(row.get("completed_at")),
        )


@dataclass
class RecurringJob:
    """
    A recurring job definition: re-enqueues a ScheduledJob on a fixed
    interval. Stored separately from one-off jobs — this is the
    *template*, not an individual run.
    """

    job_type: str
    interval_seconds: int
    payload: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    next_run_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: Optional[datetime] = None
    id: Optional[str] = None

    def to_row(self) -> dict[str, Any]:
        return {
            "job_type": self.job_type,
            "interval_seconds": self.interval_seconds,
            "payload": self.payload,
            "enabled": self.enabled,
            "next_run_at": self.next_run_at.isoformat(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "RecurringJob":
        return cls(
            id=row.get("id"),
            job_type=row["job_type"],
            interval_seconds=row["interval_seconds"],
            payload=row.get("payload") or {},
            enabled=row.get("enabled", True),
            next_run_at=_parse_dt(row.get("next_run_at")) or datetime.now(timezone.utc),
            last_run_at=_parse_dt(row.get("last_run_at")),
        )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)
