"""
synon_cache.config

ALL_CAPS_SNAKE constants pulled from environment.
"""

import os

# Which backend to use by default when Cache() is constructed with no
# explicit backend argument. "memory" requires zero infra. "redis"
# requires REDIS_URL to be set and the redis package installed.
CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "memory")

# Default TTL (seconds) applied when a call site doesn't specify one.
CACHE_DEFAULT_TTL_SECONDS: int = int(os.getenv("CACHE_DEFAULT_TTL_SECONDS", "300"))

# Redis connection (only needed if CACHE_BACKEND=redis)
REDIS_URL: str = os.getenv("REDIS_URL", "")

# Prefix applied to every key this module writes — keeps your cache
# namespaced if Redis/the cache is shared across multiple products
# or services hitting the same instance.
CACHE_KEY_PREFIX: str = os.getenv("CACHE_KEY_PREFIX", "synon")
