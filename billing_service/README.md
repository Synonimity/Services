# KerfSuite Billing Service

A standalone FastAPI subscription-billing microservice for South Africa,
using **PayFast** (Stripe isn't available here). Decoupled from any
particular auth system — it identifies people by a plain
`external_user_id` string your app gives it, so it drops into any app
regardless of how that app does login.

## ⚠️ Before you trust this with real money

PayFast's official docs site (developers.payfast.co.za) is fully
JavaScript-rendered, so I couldn't scrape its exact rules directly. What's
implemented here is built from:
- PayFast's documented field list for the checkout form
- A specific, well-documented fix for a bug in PayFast's own sample
  signature code (their sample mishandles spaces and field ordering) —
  cross-checked against several independent third-party PayFast
  integrations that all agree on the field list and order
- The subscriptions management API (pause/cancel/unpause) is the
  **least** verified part — the header-signing scheme is reconstructed
  from a single third-party example, not PayFast's own docs

**Test every code path in PayFast's sandbox before going live**,
especially: a full checkout → ITN → active subscription cycle, and each
subscription-management action (pause/unpause/cancel) against a real
sandbox token. The included signature logic is internally consistent and
unit-tested (order-independent, tamper-detecting) but I could not test it
against a live PayFast endpoint from this environment.

## How it fits together

```
Your app's backend          This service                PayFast
  │                            │                            │
  │ POST /billing/checkout ───>│                            │
  │   (X-API-Key)              │ creates pending            │
  │<── redirect_url ───────────│ subscription row           │
  │                            │                            │
  │ (redirect browser to redirect_url) ──────────────────────>│
  │                            │                            │ customer pays
  │                            │<── ITN webhook ─────────────│
  │                            │ verifies + activates        │
  │                            │ subscription                │
  │                            │                            │
  │ GET .../subscriptions ────>│                            │
  │<── current status ─────────│                            │
```

Your backend never talks to PayFast directly — it calls this service,
which calls PayFast. Your frontend only ever sees the `redirect_url`.

## 1. Set up Supabase

Run `schema.sql` in the Supabase SQL editor, then seed at least one plan
(an example insert is commented at the bottom of that file).

## 2. Set up PayFast

1. Create an account at [payfast.co.za](https://www.payfast.co.za) (and a
   separate one at [sandbox.payfast.co.za](https://sandbox.payfast.co.za)
   for testing — sandbox credentials are unrelated to live ones).
2. Settings → Integration: note your Merchant ID and Merchant Key.
3. Set a **Passphrase** there too — it's required for any recurring
   billing, and must match `PAYFAST_PASSPHRASE` exactly.
4. Settings → Integration: enable ITN and make sure nothing blocks
   inbound webhooks to `{BASE_URL}/billing/itn` (it must be publicly
   reachable over HTTPS in production).

## 3. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
```

Generate your `SERVICE_API_KEY` with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/billing/plans` | API key | List active plans |
| POST | `/billing/checkout` | API key | Start a subscription, get a redirect URL |
| POST | `/billing/itn` | PayFast signature | Webhook — PayFast calls this, not you |
| GET | `/billing/customers/{external_user_id}/subscriptions` | API key | Check a user's subscription status |
| POST | `/billing/subscriptions/{id}/cancel` | API key | Cancel |
| POST | `/billing/subscriptions/{id}/pause` | API key | Pause (optional `?cycles=N`) |
| POST | `/billing/subscriptions/{id}/unpause` | API key | Resume |

All API-key routes expect an `X-API-Key` header matching `SERVICE_API_KEY`.

## 5. Security notes

- **ITN webhook auth**: PayFast can't send your API key, so `/billing/itn`
  is authenticated three other ways instead — signature verification,
  reverse-DNS host check, and PayFast's own server-to-server
  re-validation endpoint. The amount is also cross-checked against your
  plan's price before anything is recorded, so a forged or replayed
  notification can't credit the wrong amount.
- **Idempotency**: payments are logged append-only by `pf_payment_id`;
  if PayFast retries an ITN, you'll get a duplicate row rather than a
  corrupted state — worth adding a unique constraint on `pf_payment_id`
  once you confirm PayFast never legitimately reuses it for retries vs.
  genuinely new charges.
- **RLS**: same as the auth service — tables are locked out of Supabase's
  PostgREST API entirely; only this service's direct DB connection can
  reach them.
- Card details never touch this service or your database — PayFast hosts
  the actual payment page.

## 6. Extending this template

- **Once-off (non-recurring) payments**: call `payfast.build_checkout_payload()`
  without `frequency`/`cycles` — everything else is identical.
- **Webhook notifications to your app**: right now this service just
  updates its own DB. If your app needs to react immediately (e.g. unlock
  a feature), add an internal webhook call or message-queue publish at
  the end of `payfast_itn()` in `app/routers/billing.py`.
- **Linking to the KerfSuite auth service**: pass the auth service's
  `user.id` (as a string) as `external_user_id` here — no other coupling
  needed.
