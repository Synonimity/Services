# synon_webhooks

Copy-in module for receiving, verifying, deduping, and reliably
processing inbound webhooks (PayPal, Paddle, or any future provider).

**Convention:** importable Python package, not a standalone service.
Copy this folder into your project, wire it into your existing
FastAPI app, no separate process or HTTP hop.

## What it does

- Verifies webhook authenticity via a pluggable verifier (no provider
  lock-in — write one verifier class per provider)
- Dedupes using an idempotency key, so provider retries never
  double-process
- Persists every event to Supabase, queued for processing
- Retries failed handlers with exponential backoff
- Dead-letters events that exhaust retries, so they're inspectable
  instead of silently lost

## What it deliberately does NOT do

- Run its own server process or background loop — you call
  `process_due_events()` from whatever scheduler you're using (cron,
  a simple loop, or your future background-jobs module once that's
  built)
- Contain any provider-specific logic — PayPal/Paddle/etc. verifiers
  are written per-project, using `GenericHmacVerifier` as a template
  or starting point
- Run business logic on the event — that's your handler functions,
  registered per provider, called by the queue processor

## Setup

1. Copy this folder into your project.
2. Run `schema.sql` against your project's Supabase instance.
3. Copy `.env.example` values into your `.env`, fill in Supabase creds.
4. `pip install -r requirements.txt` (or merge into your project's
   existing requirements file).

## Wiring it in

```python
from fastapi import FastAPI
from synon_webhooks import build_webhook_router, WebhookStore, GenericHmacVerifier, process_due_events

app = FastAPI()
store = WebhookStore()

# One verifier per provider. Write a custom BaseVerifier subclass for
# providers with their own signature scheme (e.g. PayPal's cert-based
# verification) — GenericHmacVerifier covers simple HMAC providers.
verifiers = {
    "paddle": GenericHmacVerifier(secret="whsec_xxx", signature_header="X-Paddle-Signature"),
}

router = build_webhook_router(verifiers=verifiers, store=store)
app.include_router(router, prefix="/webhooks")


# Business logic handlers — one per provider, called by the processor
def handle_paddle_event(event):
    if event.payload.get("event_type") == "subscription.created":
        ...  # assign CDKey, update Supabase, whatever the product needs

handlers = {"paddle": handle_paddle_event}


# Call this on a schedule (cron job, simple while-loop, or your future
# background-jobs module) — NOT inside the webhook request itself.
def run_queue_tick():
    summary = process_due_events(store=store, handlers=handlers)
    print(summary)  # {"processed": 3, "succeeded": 2, "failed": 1, "skipped": 0}
```

## Writing a provider-specific verifier

Subclass `BaseVerifier` when a provider doesn't use simple HMAC (e.g.
PayPal's verification requires hitting their API to confirm the
event). See `verifiers/base.py` for the interface — two methods:
`verify()` and `extract_idempotency_key()`.

## Inspecting dead-lettered events

```python
dead = store.get_dead_lettered()
for event in dead:
    print(event.id, event.provider, event.last_error)
```

Worth wrapping this in a tiny CLI or admin route per-project if a
product ends up depending heavily on webhooks (e.g. KerfStock).

## Files

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings (ALL_CAPS_SNAKE) |
| `models.py` | `WebhookEvent`, `WebhookStatus` |
| `verifiers/base.py` | Plug-in interface for signature verification |
| `verifiers/hmac_generic.py` | Generic HMAC-SHA256 verifier |
| `store.py` | Supabase-backed persistence + idempotency checks |
| `queue_processor.py` | Retry/backoff logic |
| `router.py` | FastAPI router — the HTTP entry point |
| `schema.sql` | Supabase table + indexes |
