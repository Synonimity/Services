"""
synon_webhooks.models

PascalCase data classes representing webhook state.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class WebhookStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


@dataclass
class WebhookEvent:
    """
    A single inbound webhook event, tracked from receipt through
    to final success/failure.
    """

    provider: str  # e.g. "paypal", "paddle", "generic_hmac"
    idempotency_key: str  # provider's event id, or a hash fallback
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
    status: WebhookStatus = WebhookStatus.PENDING
    attempt_count: int = 0
    max_retries: int = 5
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    id: Optional[str] = None  # set once persisted (Supabase row id)

    def to_row(self) -> dict[str, Any]:
        """Serialize for Supabase insert/update."""
        return {
            "provider": self.provider,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "headers": self.headers,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "max_retries": self.max_retries,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "last_error": self.last_error,
            "received_at": self.received_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "WebhookEvent":
        """Deserialize from a Supabase row."""
        return cls(
            id=row.get("id"),
            provider=row["provider"],
            idempotency_key=row["idempotency_key"],
            payload=row["payload"],
            headers=row.get("headers") or {},
            status=WebhookStatus(row["status"]),
            attempt_count=row.get("attempt_count", 0),
            max_retries=row.get("max_retries", 5),
            next_retry_at=_parse_dt(row.get("next_retry_at")),
            last_error=row.get("last_error"),
            received_at=_parse_dt(row.get("received_at")) or datetime.now(timezone.utc),
            processed_at=_parse_dt(row.get("processed_at")),
        )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)
