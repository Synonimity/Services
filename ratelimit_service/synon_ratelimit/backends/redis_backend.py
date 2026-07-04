"""
synon_ratelimit.backends.redis_backend

Opt-in backend for when the limit needs to be enforced across
multiple workers/instances, not just within one process.

WHY A LUA SCRIPT: the consume operation is read-modify-write (read
current tokens, compute refill, check against capacity, write new
value). Done as separate Redis calls, two simultaneous requests could
both read the same "tokens=1" state before either writes, and both
would be allowed through — exactly the race condition
synon_scheduler's claim_jobs() and synon_licensing's claim_pool_key()
solve with a single atomic SQL statement. Redis's equivalent
mechanism is a Lua script run via EVAL — the whole script executes
as one atomic unit on the Redis server, no race window.
"""

from typing import Optional

from .base import RateLimitBackend

# KEYS[1] = bucket key
# ARGV[1] = capacity
# ARGV[2] = refill_window_seconds
# ARGV[3] = tokens_requested
# ARGV[4] = now (unix timestamp, float)
#
# Returns: {allowed (0/1), tokens_remaining (int), retry_after_seconds (float)}
_CONSUME_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_window = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local refill_rate = capacity / refill_window

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

if tokens == nil then
    tokens = capacity
    last_refill = now
end

local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
local retry_after = 0

if tokens >= requested then
    tokens = tokens - requested
    allowed = 1
else
    local deficit = requested - tokens
    retry_after = deficit / refill_rate
end

redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
-- expire the key after the full refill window of inactivity, so
-- buckets that stop being used don't sit in Redis forever
redis.call('EXPIRE', key, math.ceil(refill_window * 2))

return {allowed, math.floor(tokens), tostring(retry_after)}
"""


class RedisBackend(RateLimitBackend):
    def __init__(self, redis_url: str):
        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "synon_ratelimit: RedisBackend requires the 'redis' package. "
                "Install it with: pip install redis"
            ) from exc

        if not redis_url:
            raise ValueError("synon_ratelimit: RedisBackend requires a non-empty redis_url")

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._consume_script = self._client.register_script(_CONSUME_SCRIPT)

    def consume(
        self,
        key: str,
        capacity: int,
        refill_window_seconds: int,
        tokens_requested: int,
        now: float,
    ) -> tuple[bool, int, float]:
        allowed, tokens_remaining, retry_after = self._consume_script(
            keys=[key],
            args=[capacity, refill_window_seconds, tokens_requested, now],
        )
        return bool(int(allowed)), int(tokens_remaining), float(retry_after)

    def reset(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:
        self._client.flushdb()
