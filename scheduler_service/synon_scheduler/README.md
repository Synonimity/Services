# synon_scheduler

Copy-in module for one-off and recurring background jobs. Closes the
gap left by `synon_webhooks` — its `process_due_events()` needs
something to call it on a schedule; this is that something.

**Convention:** importable Python package, not a standalone service.
Copy this folder into your project, run one external loop (cron,
systemd timer, or a simple script) that calls `run_due_jobs()`.

## What it does

- **One-off jobs**: enqueue from app code, run once, retry with
  exponential backoff on failure, dead-letter after max retries
  (identical shape to `synon_webhooks`)
- **Recurring jobs**: register once (e.g. on app startup), re-enqueues
  itself on a fixed interval forever
- **Atomic claiming**: uses a Postgres function (`claim_jobs`) so
  overlapping worker ticks can never grab and run the same job twice
- **Stale claim recovery**: a job stuck "running" because a worker
  crashed mid-job becomes claimable again after
  `JOB_CLAIM_TIMEOUT_MINUTES`

## What it deliberately does NOT do

- Run its own loop or process — you call `run_due_jobs()` from
  whatever scheduler you're using
- Use Redis/Celery/RQ — this is a Postgres-backed polling design,
  matching `synon_webhooks` and your existing Supabase-everywhere
  convention. Fine for tens-to-hundreds of jobs; if you ever need
  high-throughput job processing (thousands/sec), that's the signal
  to introduce a real broker — not before.

## Setup

1. Copy this folder into your project.
2. Run `schema.sql` against your project's Supabase instance (creates
   both tables AND the `claim_jobs` Postgres function — don't skip
   the function, the atomic claiming depends on it).
3. Copy `.env.example` values into your `.env`.
4. `pip install -r requirements.txt` (or merge into your project's
   existing requirements file).

## Enqueueing a one-off job

```python
from synon_scheduler import SchedulerStore
from synon_scheduler.client import enqueue_job

store = SchedulerStore()

enqueue_job(store, "send_email", {"to": "user@example.com", "template": "trial_expiring"})
```

## Registering a recurring job

Call this once on app startup — it upserts, so calling it every
startup is safe and won't create duplicates.

```python
from synon_scheduler.client import register_recurring

# Run the webhooks queue every 30 seconds
register_recurring(store, "webhook_tick", interval_seconds=30)
```

## Running the worker loop

This is the one piece of "infrastructure" you need to actually run
somewhere — a process that ticks periodically.

```python
import time
from synon_scheduler import SchedulerStore, run_due_jobs

store = SchedulerStore()

def handle_send_email(job):
    payload = job.payload
    ...  # call your notifications module here

def handle_webhook_tick(job):
    from synon_webhooks import WebhookStore, process_due_events
    process_due_events(store=WebhookStore(), handlers={...})

handlers = {
    "send_email": handle_send_email,
    "webhook_tick": handle_webhook_tick,
}

while True:
    summary = run_due_jobs(store=store, handlers=handlers)
    print(summary)
    time.sleep(5)
```

In production this loop can be a tiny systemd service, a cron job
that runs the tick once and exits, or a container — whatever fits the
project. The module doesn't care, it just expects to be called.

## Inspecting dead-lettered jobs

```python
dead = store.get_dead_lettered()
for job in dead:
    print(job.id, job.job_type, job.last_error)
```

## Files

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings (ALL_CAPS_SNAKE) |
| `models.py` | `ScheduledJob`, `RecurringJob`, `JobStatus` |
| `store.py` | Supabase-backed persistence + atomic claiming |
| `runner.py` | Worker-side: claims and executes due jobs |
| `client.py` | App-side: enqueue jobs, register recurring jobs |
| `schema.sql` | Supabase tables + atomic `claim_jobs()` function |
