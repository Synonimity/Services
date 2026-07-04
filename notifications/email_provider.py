import asyncio
import logging

import httpx

logger = logging.getLogger("notifications.resend")

RESEND_API_URL = "https://api.resend.com/emails"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [1, 3, 8]


class EmailSendError(Exception):
    pass


async def send_email(
    *,
    api_key: str,
    from_header: str,
    to_email: str,
    to_name: str | None,
    subject: str,
    html: str,
    text: str,
    idempotency_key: str | None = None,
) -> str:
    """Returns the provider's message id. Raises EmailSendError on failure."""
    recipient = f"{to_name} <{to_email}>" if to_name else to_email

    body = {
        "from": from_header,
        "to": [recipient],
        "subject": subject,
        "html": html,
        "text": text,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "kerfsuite-notifications-module/1.0",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(RESEND_API_URL, json=body, headers=headers)

            if resp.status_code == 200:
                return resp.json()["id"]

            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise EmailSendError(f"Resend rejected the request ({resp.status_code}): {resp.text}")

            last_error = EmailSendError(f"Resend returned {resp.status_code}: {resp.text}")
        except httpx.TransportError as exc:
            last_error = exc

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_BACKOFF_SECONDS[attempt])

    logger.error("Email send failed after %s attempts: %s", MAX_RETRIES, last_error)
    raise EmailSendError(str(last_error))
