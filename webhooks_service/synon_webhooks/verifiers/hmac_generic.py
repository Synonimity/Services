"""
synon_webhooks.verifiers.hmac_generic

A generic HMAC-SHA256 verifier — the most common signature scheme used
by webhook providers that aren't PayPal (Paddle, Stripe-likes, custom
internal services, etc.). Use this directly, or as a reference for
writing a provider-specific verifier later.
"""

import hashlib
import hmac
from typing import Any

from .base import BaseVerifier, VerificationError


class GenericHmacVerifier(BaseVerifier):
    """
    Verifies a webhook signed with HMAC-SHA256, where the signature is
    sent in a header as a hex digest.

    Example usage:
        verifier = GenericHmacVerifier(
            secret="whsec_xxx",
            signature_header="X-Signature",
        )
    """

    provider_name = "generic_hmac"

    def __init__(
        self,
        secret: str,
        signature_header: str = "X-Signature",
        idempotency_field: str = "id",
    ):
        if not secret:
            raise ValueError("GenericHmacVerifier requires a non-empty secret")
        self._secret = secret.encode("utf-8")
        self._signature_header = signature_header
        self._idempotency_field = idempotency_field

    def verify(self, headers: dict[str, str], raw_body: bytes) -> bool:
        # Headers may arrive with inconsistent casing depending on the
        # framework — normalize to a case-insensitive lookup.
        normalized = {k.lower(): v for k, v in headers.items()}
        signature = normalized.get(self._signature_header.lower())

        if not signature:
            raise VerificationError(
                f"Missing signature header: {self._signature_header}"
            )

        expected = hmac.new(self._secret, raw_body, hashlib.sha256).hexdigest()

        # constant-time comparison — never use == for signatures
        if not hmac.compare_digest(expected, signature):
            raise VerificationError("Signature mismatch")

        return True

    def extract_idempotency_key(self, headers: dict[str, str], payload: dict[str, Any]) -> str:
        key = payload.get(self._idempotency_field)
        if not key:
            raise VerificationError(
                f"Payload missing idempotency field: {self._idempotency_field}"
            )
        return str(key)
