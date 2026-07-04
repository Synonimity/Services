# KerfSuite Observability Service

Structured logging + Sentry-style error tracking in one service, since an
error report is really just a special, grouped kind of log entry. Ships
with a drop-in Python client so wiring up a new app is a few lines.

## How the two modules relate

- **`/logs`** — raw, append-only structured log lines. Cheap, high
  volume, queryable, with a retention/cleanup endpoint since this table
  will grow fast.
- **`/errors`** — exceptions get grouped into **issues** by a fingerprint
  (service + environment + exception type + a normalized version of the
  message, with numbers/UUIDs/quoted strings stripped out so "User '123'
  not found" and "User '456' not found" group as one issue instead of two).
  Each issue tracks an occurrence count, first/last seen, and status
  (open/resolved/ignored). A resolved issue that happens again is flagged
  as a **regression** and reopened automatically.

Fingerprinting is a heuristic, not a guarantee — it's deliberately
language-agnostic rather than parsing stack frames (which differ wildly
between Python/JS/Go/etc). If grouping is too loose or too tight for a
specific error, pass `fingerprint_override` in the report and bypass it
entirely.

## Connecting to the notifications service (optional but recommended)

Set `NOTIFICATIONS_BASE_URL` + `NOTIFICATIONS_API_KEY` and this service
will ping Slack/Discord (via the notifications service built earlier)
the moment a **new** error issue appears, or a resolved one **regresses**.
This call is fire-and-forget on a background task — error reporting
itself never slows down or fails because an alert couldn't be delivered
(this is unit-tested: an unreachable notifications endpoint logs a
warning and the report still succeeds).

## 1. Set up Supabase

Run `schema.sql`. It includes a commented-out `pg_cron` snippet for
automatic daily log cleanup if you'd rather not hit `DELETE /logs/cleanup`
from an external scheduler.

## 2. Install and run

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
```

## 3. Plug it into a Python app

```python
import logging
from client.logging_handler import RemoteLogHandler, install_fastapi_error_reporting

handler = RemoteLogHandler(
    base_url="https://obs.kerfsuite.com",
    api_key="...",
    service_name="kerfportal",       # whatever you want it labelled as
    environment="production",
)
handler.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(handler)   # every logger.info/warning/error now also goes here

# Optional, FastAPI apps only - auto-reports any unhandled exception
# with the request path/method attached as context:
install_fastapi_error_reporting(app, handler)
```

That's it — `logger.error("...", exc_info=True)` anywhere in the app now
also creates/updates a grouped issue, with the full traceback attached.
The handler batches and sends on a background thread; if the network call
fails, it's swallowed silently rather than crashing your app or blocking
the request that triggered the log line. Copy `client/logging_handler.py`
into any other Python project — it has no dependency on the rest of this
repo, just `httpx`.

Not using Python, or want to call it directly? `POST /errors/report` and
`POST /logs` are plain JSON over HTTP — see `app/schemas.py` for the exact
shape.

## 4. Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/logs` | Ingest a batch of log entries |
| GET | `/logs` | Query logs (filter by service/level/user/request_id/text search) |
| DELETE | `/logs/cleanup` | Delete entries older than `LOG_RETENTION_DAYS` |
| POST | `/errors/report` | Report an exception occurrence (creates/updates an issue) |
| GET | `/errors` | List issues (filter by service/environment/status) |
| GET | `/errors/{id}` | Issue detail + 20 most recent occurrences |
| POST | `/errors/{id}/resolve` | Mark resolved |
| POST | `/errors/{id}/ignore` | Mark ignored (still counted, no realert) |

All routes require an `X-API-Key` header — there's no public webhook
endpoint on this service, unlike the billing/notifications ones, since
nothing external calls it unprompted.

## 5. Connecting to the other services

- Wrap each existing service's startup with the same handler (`service_name="auth"`,
  `"billing"`, `"notifications"`) and you get a unified error/log view
  across all of KerfSuite from one place.
- In the billing service's `payfast_itn()`, an `except` block reporting to
  `/errors/report` would catch integration issues with PayFast itself
  (distinct from a customer's payment simply failing, which is expected
  and already handled there).

## 6. Notes on scale

Postgres handles this fine at small-to-medium volume, but a single table
taking every log line from every app will eventually get big. The
retention cleanup endpoint/cron keeps `log_entries` bounded; `error_issues`
and `error_occurrences` are kept indefinitely since they're much lower
volume (one row per *unique* bug, not per occurrence... mostly — consider
also pruning old `error_occurrences` rows beyond the most recent N per
issue if you start tracking very high-frequency errors).
