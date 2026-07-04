"""
Resend signs webhooks using Svix's standard webhook scheme. Implemented
directly against the public Svix spec rather than pulling in the svix
package, to keep this service's dependency footprint small.

Spec: signed_content = "{svix-id}.{svix-timestamp}.{raw_body}"
      signature       = base64(HMAC-SHA256(secret_bytes, signed_content))
      header           = "v1,<sig1> v1,<sig2> ..." (space-separated, for
                          secret rotation - any match is valid)
"""
import base64
import hashlib
import hmac
import time

MAX_TIMESTAMP_SKEW_SECONDS = 5 * 60


class WebhookVerificationError(Exception):
    pass


def verify_svix_signature(
    *,
    secret: str,
    raw_body: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
) -> None:
    """Raises WebhookVerificationError if the signature doesn't check out."""
    if not (secret and svix_id and svix_timestamp and svix_signature):
        raise WebhookVerificationError("Missing webhook headers or secret.")

    try:
        timestamp = int(svix_timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Malformed svix-timestamp.") from exc

    if abs(time.time() - timestamp) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise WebhookVerificationError("Webhook timestamp outside tolerance window (possible replay).")

    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    signed_content = f"{svix_id}.{svix_timestamp}.{raw_body.decode()}".encode()
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()

    candidates = svix_signature.split(" ")
    for candidate in candidates:
        _, _, sig = candidate.partition(",")
        if sig and hmac.compare_digest(sig, expected):
            return

    raise WebhookVerificationError("Signature mismatch.")
