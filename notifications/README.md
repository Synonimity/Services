# Notifications — Copy-in Module

Drop this folder into any FastAPI project. Handles transactional email
(via Resend), delivery tracking (via Resend's Svix-signed webhooks), and
ops alerts to Slack/Discord. No separate process, no inter-service HTTP
for anything except the Resend webhook endpoint which genuinely needs to
be reachable from outside.

## Drop-in steps

**1. Copy the folder**
```
your_project/
    notifications/       ← this folder
    main.py
    ...
```

**2. Add dependencies**
```
# requirements.txt
httpx==0.27.2
jinja2==3.1.4
email-validator==2.2.0
```

**3. Run schema.sql** in your Supabase project's SQL editor.

**4. Wire into your host app**

```python
# main.py (or wherever you build your FastAPI app)
from notifications import NotificationsConfig, NotificationsService, make_router

# Build from wherever your app already gets config
notifications_cfg = NotificationsConfig(
    resend_api_key=settings.resend_api_key,
    resend_webhook_secret=settings.resend_webhook_secret,
    email_from_address=settings.email_from_address,
    email_from_name="KerfSuite",
    brand_name="KerfSuite",
    brand_color="#FF6A00",
    brand_footer_text="SynonTech, Johannesburg",
    slack_webhook_url=settings.slack_webhook_url,
)
notifications = NotificationsService(notifications_cfg)

# Mount the router — only the Resend webhook actually needs to be HTTP.
# send(), get_status(), trigger_alert() are called directly in Python.
app.include_router(make_router(notifications, db_dep=get_db))
```

**5. Call it from your own code**

```python
from notifications import NotificationsService, SendEmailRequest

# Anywhere in your own request handlers / background tasks:
async def register_user(user, db):
    # ... create user ...
    await notifications.send(db, SendEmailRequest(
        template_name="welcome",
        to_email=user.email,
        to_name=user.name,
        external_user_id=str(user.id),
        variables={"name": user.name, "cta_url": "https://app.example.com"},
    ))

# Ops alert from a background job:
from notifications import AlertRequest
await notifications.trigger_alert(AlertRequest(
    channel="slack",
    title="Payment failed",
    message=f"Subscription {sub_id} payment failed",
    severity="error",
    fields={"user": user_email, "plan": plan_name},
))
```

## Adding email templates

Add a folder under `notifications/templates/<name>/` with:
- `subject.txt` — Jinja2, brand vars available
- `body.html` — Jinja2, extends `_layout.html`

No code changes needed — it shows up in `list_templates()` immediately.

## Config reference

| Field | Required | Description |
|---|---|---|
| `resend_api_key` | Yes | From resend.com/api-keys |
| `resend_webhook_secret` | No | From Resend dashboard → Webhooks. Needed for delivery tracking. |
| `email_from_address` | Yes | e.g. `noreply@yourdomain.com` |
| `email_from_name` | No | Display name in the From header |
| `brand_name` | No | Used in email templates |
| `brand_color` | No | Hex, used in email template header |
| `brand_logo_url` | No | Optional logo URL |
| `brand_footer_text` | No | Footer text in every email |
| `slack_webhook_url` | No | Leave blank to disable Slack alerts |
| `discord_webhook_url` | No | Leave blank to disable Discord alerts |

## Webhook endpoint

The Resend webhook needs to be publicly reachable at whatever URL you
mount the router on. Configure it in Resend's dashboard:
`https://yourdomain.com/notifications/webhooks/resend`

Verified via Svix HMAC signature + 5-minute timestamp replay protection.
