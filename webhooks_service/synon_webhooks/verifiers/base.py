"""
synon_webhooks.verifiers.base

The plug-in interface. Every provider-specific verifier (PayPal, Paddle,
a future product's payment processor, etc.) implements this. The router
never knows about specific providers — it just calls .verify() on
whatever verifier is registered for the incoming route.
"""

from abc import ABC, abstractmethod
from typing import Any


class VerificationError(Exception):
    """Raised when a webhook fails signature/authenticity verification."""


class BaseVerifier(ABC):
    """
    Subclass this for each provider. Keep verifiers stateless and pure —
    they take headers + raw body, return True/raise, nothing else.
    """

    #: Override with a short identifier, e.g. "paypal", "paddle"
    provider_name: str = "unknown"

    @abstractmethod
    def verify(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify the webhook is authentic.

        Args:
            headers: raw request headers (case-insensitive dict recommended)
            raw_body: the exact raw request body bytes (NOT re-serialized
                      JSON — signatures are computed over raw bytes, and
                      re-serializing can silently break verification)

        Returns:
            True if verified.

        Raises:
            VerificationError if verification fails. Don't return False —
            raising forces callers to handle it explicitly rather than
            accidentally ignoring a falsy return value.
        """
        raise NotImplementedError

    @abstractmethod
    def extract_idempotency_key(self, headers: dict[str, str], payload: dict[str, Any]) -> str:
        """
        Pull a stable unique identifier for this event out of the
        payload/headers (e.g. PayPal's `id` field, or a provider's
        delivery ID header). Used for dedupe.
        """
        raise NotImplementedError
