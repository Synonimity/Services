"""
synon_webhooks.queue_processor

Retry/backoff logic. Call `process_due_events()` from a scheduled job
(cron, your future background-jobs module, or a simple while-loop
worker) — this module doesn't run its own loop, it just processes
whatever's due when called, so it plugs into whatever scheduler you
end up standardizing on.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from .models import WebhookEvent
from .store import WebhookStore

logger = logging.getLogger("synon_webhooks")

# A handler takes the verified, deduped event and does the actual
# business logic (e.g. "assign a CDKey", "mark order paid"). Raise
# any exception to signal failure -> triggers retry/backoff.
EventHandler = Callable[[WebhookEvent], None]


def compute_backoff_seconds(attempt_count: int, config) -> int:
    """
    Exponential backoff: base * 2^attempt, capped at max.
    """
    backoff = config.base_backoff_seconds * (2**attempt_count)
    return min(backoff, config.max_backoff_seconds)


def process_due_events(
    store: WebhookStore,
    handlers: dict[str, EventHandler],
    limit: int = 50,
) -> dict[str, int]:
    """
    Process all due events.
    """
    summary = {"processed": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    for event in store.claim_due_events(limit=limit):
        summary["processed"] += 1
        handler = handlers.get(event.provider)

        if handler is None:
            logger.warning(
                "synon_webhooks: no handler registered for provider '%s', skipping event %s",
                event.provider,
                event.id,
            )
            # Put it back as pending rather than leaving it stuck
            # "processing" with no handler ever able to claim it again.
            store.mark_failed(event, error="no handler registered", next_retry_at=None)
            summary["skipped"] += 1
            continue

        try:
            handler(event)
            store.mark_succeeded(event)
            summary["succeeded"] += 1
        except Exception as exc:  # noqa: BLE001
            backoff_seconds = compute_backoff_seconds(event.attempt_count, store.config)
            next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

            logger.error(
                "synon_webhooks: handler failed for event %s (provider=%s, attempt=%d): %s",
                event.id,
                event.provider,
                event.attempt_count + 1,
                exc,
                exc_info=True,
            )

            store.mark_failed(event, error=str(exc), next_retry_at=next_retry_at)
            summary["failed"] += 1

    return summary
