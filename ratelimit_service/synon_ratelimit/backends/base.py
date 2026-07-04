"""
synon_ratelimit.backends.base

Same plug-in pattern as synon_cache.backends.base, but the interface
is shaped for token buckets specifically: a backend needs to store
(tokens_remaining, last_refill_timestamp) per key, and the consume
operation must be atomic — two simultaneous requests checking the
same key must not both succeed past the limit due to a race between
read and write.
"""

from abc import ABC, abstractmethod
from typing import Optional


class RateLimitBackend(ABC):
    """
    Subclass this to add a new storage backend. `consume` is the only
    method that matters for correctness — it must atomically check
    whether a token is available and decrement if so, in one
    operation, not a separate read-then-write that another caller
    could interleave with.
    """

    @abstractmethod
    def consume(
        self,
        key: str,
        capacity: int,
        refill_window_seconds: int,
        tokens_requested: int,
        now: float,
    ) -> tuple[bool, int, float]:
        """
        Attempt to consume `tokens_requested` tokens from the bucket
        identified by `key`.

        Args:
            key: namespaced bucket identifier
            capacity: max tokens the bucket can hold (also the refill
                      target — bucket refills to full over
                      refill_window_seconds)
            refill_window_seconds: time for the bucket to fully refill
                                    from empty to `capacity`
            tokens_requested: how many tokens this request costs
                               (usually 1, but supports weighting
                               expensive operations higher)
            now: current time as a unix timestamp (passed in rather
                 than called internally, so tests can control time
                 deterministically)

        Returns:
            (allowed, tokens_remaining, retry_after_seconds)
            - allowed: True if the request should proceed
            - tokens_remaining: tokens left in the bucket after this call
            - retry_after_seconds: if not allowed, how long until
              enough tokens will be available (0 if allowed)
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self, key: str) -> None:
        """Resets a bucket to full capacity. Mostly for tests/admin override."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Removes all bucket state this backend is holding. Mostly for tests."""
        raise NotImplementedError
