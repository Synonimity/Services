# KerfSuite Notifications Service

A standalone FastAPI service for transactional email and ops alerts.
Decoupled from any particular auth/billing system, same as the others —
it just needs an email address and (optionally) your app's own user ID.

## Confidence notes

- **Email sending (Resend) and webhook verification (Svix)**: built from
  Resend's published REST API and the public Svix signing spec, both of
  which are stable and well-documented. The Svix verification is
  unit-tested in this repo against hand-computed signatures (valid,
  tampered, replayed, rotated-secret cases) — all pass.
- Still: send a real test email through sandbox/your own inbox and fire a
  real webhook from the Resend dashboard's "Send test event" button before
  relying on this in production. No amount of unit testing replaces that.

## How it fits together

```
Your app's backend                This service              Resend
  │                                    │                       │
  │ POST /notifications/send ────────>│                       │
  │  (X-API-Key, template + vars)     │ renders Jinja2 template│
  │                                    │ POST /emails ────────>│
  │<── {id, status: "sent"} ───────────│                       │
  │                                    │                       │
  │                                    │<── webhook (delivered/│
  │                                    │     bounced/opened) ──│
  │                                    │ verifies Svix sig,     │
  │                                    │ updates status         │
  │ GET /notifications/{id} ──────────>│                       │
  │<── current status ──────────────────│                       │
```

Separately, `POST /notifications/alert` pings Slack or Discord directly —
no templates, no DB logging, just a quick ops ping.

## 1. Set up Supabase

Run `schema.sql` in the Supabase SQL editor.

## 2. Set up Resend

1. Sign up at [resend.com](https://resend.com), add and verify a sending
   domain (Resend gives you SPF/DKIM DNS records to add).
2. Create an API key (Settings → API Keys) — sending-only access is
   enough, you don't need full account access.
3. Settings → Webhooks → add an endpoint pointing at
   `{BASE_URL}/notifications/webhooks/resend`, select the event types you
   care about (at minimum: `email.delivered`, `email.bounced`,
   `email.complained`, `email.failed`), and copy the signing secret into
   `RESEND_WEBHOOK_SECRET`.

## 3. Set up Slack/Discord alerts (optional)

- **Slack**: create an Incoming Webhook in your workspace (api.slack.com/apps
  → your app → Incoming Webhooks) and paste the URL into `SLACK_WEBHOOK_URL`.
- **Discord**: a channel's Settings → Integrations → Webhooks → New
  Webhook gives you a URL for `DISCORD_WEBHOOK_URL`.

Leave either blank to disable that channel — `/notifications/alert` will
return a clear 502 error if you try to use an unconfigured one, rather
than silently failing.

## 4. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
```

## 5. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/notifications/templates` | API key | List available email templates |
| POST | `/notifications/send` | API key | Render a template and send it |
| GET | `/notifications/{id}` | API key | Check delivery status of a send |
| POST | `/notifications/webhooks/resend` | Svix signature | Resend calls this, not you |
| POST | `/notifications/alert` | API key | Ping Slack/Discord |

### Sending an email

```bash
curl -X POST https://notify.yourapp.com/notifications/send \
  -H "X-API-Key: $SERVICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "template_name": "welcome",
    "to_email": "user@example.com",
    "to_name": "Bruce",
    "external_user_id": "usr_123",
    "variables": {"name": "Bruce", "cta_url": "https://app.example.com/start"}
  }'
```

### One-off emails without a template

Use `template_name: "generic"` and pass `subject` and `html_content` directly
in `variables` — it still goes through the shared branded layout.

## 6. Adding a new email type

Add a folder under `app/templates/<name>/` with `subject.txt` and
`body.html` (the latter extending `_layout.html`). No code changes needed
— it shows up automatically in `/notifications/templates` and is usable
immediately via `template_name`.

## 7. Connecting to the other services

- **Billing service**: in `payfast_itn()`, after a `FAILED` payment_status
  or a cancellation, call `POST /notifications/send` with
  `template_name: "payment_failed"` or `"subscription_cancelled"`, and
  `POST /notifications/alert` with `severity: "warning"` to flag it to you.
- **Auth service**: call `POST /notifications/send` with
  `template_name: "welcome"` right after registration, and
  `"email_verification"` / `"password_reset"` for those flows — the auth
  service doesn't send email itself by design, so this is what fills that gap.

## 8. Security notes

- The Resend webhook is authenticated via Svix HMAC signature + a 5-minute
  timestamp tolerance window (replay protection) — not by IP or API key,
  since Resend can't send your `X-API-Key`.
- `idempotency_key` is enforced both at this service's DB layer (unique
  constraint) and passed through to Resend's own `Idempotency-Key` header,
  so a retried request from your backend can never double-send.
- Same RLS lockdown pattern as the other services: tables aren't reachable
  via Supabase's PostgREST API, only via this service's direct connection.
