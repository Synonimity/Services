# synon_usage_tracker

Tracks per-user token usage and cost, and enforces plan-based quotas.
Sits alongside `synon_licensing` / `synon_ratelimit` — this module owns
"how much has this user used, and are they over their limit," nothing
more. It doesn't call the LLM or gate requests itself; you call it before
and after your own `llm_caller.py` call.

## Quick start

```python
from usage_tracker import UsageTracker
from backends import InMemoryBackend

tracker = UsageTracker(backend=InMemoryBackend())

# Before the request: check quota
quota = tracker.check_quota(user_id="user_123", plan="trial")
if not quota.within_limit:
    raise Exception(quota.reason)

# ... call the LLM via llm_caller.py, get input/output token counts back ...

# After the request: record it
event = tracker.record(
    user_id="user_123",
    model="claude-sonnet-5",
    input_tokens=850,
    output_tokens=412,
    session_id="session_abc",   # optional
)
print(event.cost)   # e.g. 0.008805

# Anytime: pull totals for a dashboard
totals = tracker.get_totals("user_123", period="month")
print(totals.total_tokens, totals.cost)
```

## Plans & quotas (`plans.py`)

```python
PLAN_LIMITS = {
    "trial": {"max_tokens_per_period": 200_000, "max_cost_per_period": None, "period": "month"},
    "pro":   {"max_tokens_per_period": None,     "max_cost_per_period": 50.00, "period": "month"},
    "unlimited": {"max_tokens_per_period": None, "max_cost_per_period": None, "period": "month"},
}
```

`None` means unlimited for that dimension. A plan can gate on tokens,
cost, both, or neither. `period` is `"day"`, `"month"`, or `"all"`. Add
as many plans as you need — the tracker just looks them up by name.

## Pricing (`pricing.py`)

`MODEL_PRICING` is USD per 1,000,000 tokens, input/output split, matching
how most providers publish pricing. Unknown models fall back to
`DEFAULT_PRICING` rather than raising — a stale pricing table shouldn't
crash a live request. Update this file whenever pricing changes; nothing
else needs to change.

## Backends

- `InMemoryBackend` — zero setup, data lives for the process lifetime.
  Good for local dev/tests.
- `SupabaseBackend` — persists every event to `usage_events` (see
  `schema.sql`). Requires `SUPABASE_URL` + `SUPABASE_KEY` (service role)
  and the `supabase` package. RLS locked down by default, same posture as
  the rest of the library — access goes through your server, not
  anon/authenticated clients directly.

## Notes

- `record()` computes cost at write time using whatever `pricing.py` says
  *right now* — if you change prices later, historical events keep their
  original recorded cost (they're not recalculated retroactively).
- `check_quota()` re-aggregates from stored events each call rather than
  keeping a running counter, so it's always correct even if events come
  from multiple app instances — the tradeoff is it costs a query. Cache
  the result at the request level if you're calling it on every single
  message in a fast conversation loop.
