"""
synon_scheduler.config

ALL_CAPS_SNAKE constants pulled from environment. Mirrors
synon_webhooks.config — same Supabase project, same conventions.
"""

import os


# --- Supabase connection (reuse your existing project's creds) ---
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- Retry / backoff behaviour (one-off jobs) ---
JOB_MAX_RETRIES: int = int(os.getenv("JOB_MAX_RETRIES", "5"))
JOB_BASE_BACKOFF_SECONDS: int = int(os.getenv("JOB_BASE_BACKOFF_SECONDS", "30"))
JOB_MAX_BACKOFF_SECONDS: int = int(os.getenv("JOB_MAX_BACKOFF_SECONDS", "3600"))

# --- Claiming behaviour ---
# How long a job can sit "claimed" before another worker tick is
# allowed to assume the original run crashed and re-claim it. Protects
# against a worker dying mid-job and leaving it stuck "running" forever.
JOB_CLAIM_TIMEOUT_MINUTES: int = int(os.getenv("JOB_CLAIM_TIMEOUT_MINUTES", "15"))

# --- Table names (override if you namespace per-product) ---
JOBS_TABLE: str = os.getenv("JOBS_TABLE", "scheduled_jobs")
RECURRING_JOBS_TABLE: str = os.getenv("RECURRING_JOBS_TABLE", "recurring_jobs")


def validate_config() -> None:
    """Call this on startup. Fails loudly instead of silently misbehaving."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(
            f"synon_scheduler: missing required env vars: {', '.join(missing)}"
        )
