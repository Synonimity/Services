"""
synon_webhooks.store

Supabase-backed persistence for webhook events: idempotency checks,
queue state, retry bookkeeping. Requires the `webhook_events` table
(see schema.sql) to exist in your project's Supabase instance.

NOTE: uses the service_role client, same convention as your other
KerfSuite services — all writes happen server-side, never via an
anon/authenticated RLS path.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client, create_client

from .config import WebhooksConfig
from .models import WebhookEvent, WebhookStatus


class WebhookStore:
    def __init__(self, config: WebhooksConfig, client: Optional[Client] = None):
        self.config = config
        if client is not None:
            self._client = client
        else:
            self._client = create_client(
                config.supabase_url, config.supabase_service_role_key
            )
        self._table = config.events_table

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def already_processed(self, provider: str, idempotency_key: str) -> bool:
        """
        True if this exact event has already succeeded within the
        idempotency window.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.config.idempotency_window_hours
        )
        result = (
            self._client.table(self._table)
            .select("id")
            .eq("provider", provider)
            .eq("idempotency_key", idempotency_key)
            .eq("status", WebhookStatus.SUCCEEDED.value)
            .gte("processed_at", cutoff.isoformat())
            .limit(1)
            .execute()
        )
        return len(result.data) > 0

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert(self, event: WebhookEvent) -> WebhookEvent:
        result = self._client.table(self._table).insert(event.to_row()).execute()
        row = result.data[0]
        event.id = row["id"]
        return event

    def mark_succeeded(self, event: WebhookEvent) -> None:
        event.status = WebhookStatus.SUCCEEDED
        event.processed_at = datetime.now(timezone.utc)
        self._update(event)

    def mark_failed(self, event: WebhookEvent, error: str, next_retry_at: Optional[datetime]) -> None:
        event.attempt_count += 1
        event.last_error = error[:2000]  # don't let a giant traceback blow up the row

        if next_retry_at is not None and event.attempt_count < event.max_retries:
            event.status = WebhookStatus.PENDING
            event.next_retry_at = next_retry_at
        else:
            event.status = WebhookStatus.DEAD_LETTERED
            event.next_retry_at = None

        self._update(event)

    def mark_processing(self, event: WebhookEvent) -> None:
        event.status = WebhookStatus.PROCESSING
        self._update(event)

    def _update(self, event: WebhookEvent) -> None:
        self._client.table(self._table).update(event.to_row()).eq("id", event.id).execute()

    # ------------------------------------------------------------------
    # Reads (for the queue processor)
    # ------------------------------------------------------------------

    def claim_due_events(self, limit: int = 50) -> list[WebhookEvent]:
        """
        Atomically claims up to `limit` due events by calling the
        `claim_webhook_events` Postgres function (see schema.sql).
        This avoids the race condition of SELECT-then-UPDATE across
        overlapping worker ticks.
        """
        now = datetime.now(timezone.utc)
        result = self._client.rpc(
            "claim_webhook_events",
            {
                "p_table": self._table,
                "p_limit": limit,
                "p_now": now.isoformat(),
            },
        ).execute()

        return [WebhookEvent.from_row(row) for row in result.data]

    def get_dead_lettered(self, limit: int = 50) -> list[WebhookEvent]:
        """For a dashboard/CLI to inspect events that exhausted retries."""
        result = (
            self._client.table(self._table)
            .select("*")
            .eq("status", WebhookStatus.DEAD_LETTERED.value)
            .order("received_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [WebhookEvent.from_row(row) for row in result.data]
