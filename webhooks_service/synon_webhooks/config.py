"""
synon_webhooks.config

ALL_CAPS_SNAKE constants pulled from environment.
Wire this through your existing env-handling module if you have a
central loader — this file just defines what webhooks needs.
"""

import os


# --- Supabase connection (reuse your existing project's creds) ---
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- Retry / backoff behaviour ---
WEBHOOK_MAX_RETRIES: int = int(os.getenv("WEBHOOK_MAX_RETRIES", "5"))
WEBHOOK_BASE_BACKOFF_SECONDS: int = int(os.getenv("WEBHOOK_BASE_BACKOFF_SECONDS", "30"))
WEBHOOK_MAX_BACKOFF_SECONDS: int = int(os.getenv("WEBHOOK_MAX_BACKOFF_SECONDS", "3600"))

# --- Idempotency ---
# How long a processed event's idempotency key is considered valid
# before it's allowed to be reprocessed (covers provider retries that
# arrive long after the original event).
WEBHOOK_IDEMPOTENCY_WINDOW_HOURS: int = int(
    os.getenv("WEBHOOK_IDEMPOTENCY_WINDOW_HOURS", "72")
)

# --- Table names (override if you namespace per-product) ---
WEBHOOK_EVENTS_TABLE: str = os.getenv("WEBHOOK_EVENTS_TABLE", "webhook_events")


def validate_config() -> None:
    """Call this on startup. Fails loudly instead of silently misbehaving."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(
            f"synon_webhooks: missing required env vars: {', '.join(missing)}"
        )
