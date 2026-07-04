"""
synon_licensing.config

ALL_CAPS_SNAKE constants pulled from environment. Same conventions as
synon_webhooks and synon_scheduler — same Supabase project.
"""

import os


# --- Supabase connection (reuse your existing project's creds) ---
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# --- Key generation ---
# Format: XXXX-XXXX-XXXX-XXXX, uppercase alphanumeric, no ambiguous
# chars (0/O, 1/I/L excluded) — matches the kind of key a customer
# can read aloud or type without confusion.
LICENSE_KEY_SEGMENT_LENGTH: int = int(os.getenv("LICENSE_KEY_SEGMENT_LENGTH", "4"))
LICENSE_KEY_SEGMENT_COUNT: int = int(os.getenv("LICENSE_KEY_SEGMENT_COUNT", "4"))

# --- Table names (override if you namespace per-product) ---
LICENSE_KEYS_TABLE: str = os.getenv("LICENSE_KEYS_TABLE", "license_keys")
LICENSE_KEY_POOL_TABLE: str = os.getenv("LICENSE_KEY_POOL_TABLE", "license_key_pool")
TRIAL_USAGE_TABLE: str = os.getenv("TRIAL_USAGE_TABLE", "trial_usage")


def validate_config() -> None:
    """Call this on startup. Fails loudly instead of silently misbehaving."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(
            f"synon_licensing: missing required env vars: {', '.join(missing)}"
        )
