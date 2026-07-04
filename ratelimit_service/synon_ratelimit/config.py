"""
synon_ratelimit.config

ALL_CAPS_SNAKE constants pulled from environment. Mirrors
synon_cache's backend-selection pattern.
"""

import os

# "memory" (default, zero infra, per-process) or "redis" (shared
# across workers/instances). Same tradeoffs as synon_cache — memory
# is fine for a single-process app, Redis is needed once a product
# runs multiple workers and the limit needs to be enforced GLOBALLY
# rather than per-worker.
RATELIMIT_BACKEND: str = os.getenv("RATELIMIT_BACKEND", "memory")

REDIS_URL: str = os.getenv("REDIS_URL", "")

# Default bucket settings applied when a call site doesn't specify
# its own. "10 requests per 60 seconds" is a reasonable generic
# default — override per-route/per-key as needed.
RATELIMIT_DEFAULT_CAPACITY: int = int(os.getenv("RATELIMIT_DEFAULT_CAPACITY", "10"))
RATELIMIT_DEFAULT_WINDOW_SECONDS: int = int(os.getenv("RATELIMIT_DEFAULT_WINDOW_SECONDS", "60"))

RATELIMIT_KEY_PREFIX: str = os.getenv("RATELIMIT_KEY_PREFIX", "synon_rl")
