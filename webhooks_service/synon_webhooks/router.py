"""
synon_webhooks.router

Mount this into your existing FastAPI app:

    from synon_webhooks.router import build_webhook_router
    from synon_webhooks.verifiers import GenericHmacVerifier

    router = build_webhook_router(
        verifiers={
            "paddle": GenericHmacVerifier(secret=PADDLE_SECRET, signature_header="X-Paddle-Signature"),
        },
        store=WebhookStore(),
    )
    app.include_router(router, prefix="/webhooks")

Each provider gets its own route: POST /webhooks/{provider}
This endpoint ONLY verifies + persists + dedupes. It does NOT run
business logic — that happens later when queue_processor calls your
registered handler. Keeps the webhook receipt path fast (important —
most providers expect a 2xx within a few seconds or they'll consider
delivery failed and retry anyway).
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from .models import WebhookEvent
from .store import WebhookStore
from .verifiers.base import BaseVerifier, VerificationError

logger = logging.getLogger("synon_webhooks")


def build_webhook_router(
    verifiers: dict[str, BaseVerifier],
    store: WebhookStore,
) -> APIRouter:
    router = APIRouter()

    @router.post("/{provider}")
    async def receive_webhook(provider: str, request: Request):
        verifier = verifiers.get(provider)
        if verifier is None:
            # Don't leak which providers ARE configured to an attacker
            # probing endpoints.
            raise HTTPException(status_code=404, detail="Not found")

        raw_body = await request.body()
        headers = dict(request.headers)

        try:
            verifier.verify(headers, raw_body)
        except VerificationError as exc:
            logger.warning("synon_webhooks: verification failed for provider '%s': %s", provider, exc)
            raise HTTPException(status_code=401, detail="Verification failed") from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        idempotency_key = verifier.extract_idempotency_key(headers, payload)

        if store.already_processed(provider, idempotency_key):
            # Not an error — this is the expected, healthy outcome of a
            # provider retrying delivery. Acknowledge and move on.
            logger.info(
                "synon_webhooks: duplicate event ignored (provider=%s, key=%s)",
                provider,
                idempotency_key,
            )
            return {"status": "duplicate_ignored"}

        event = WebhookEvent(
            provider=provider,
            idempotency_key=idempotency_key,
            payload=payload,
            headers=headers,
        )
        store.insert(event)

        return {"status": "queued", "event_id": event.id}

    return router
