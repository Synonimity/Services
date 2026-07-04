# synon_licensing

Copy-in module for issuing, validating, and revoking license keys —
with optional trial constraints (time-based, run-count-based, or
both) and optional machine-binding. Generalizes the CDKey pattern
already running in KerfCut.

**Convention:** importable Python package, not a standalone service.
Copy this folder into your project, wire it directly into your app
code and your webhook/scheduler handlers.

## What it does

- **Two issuance modes**, same underlying assignment logic:
  - `POOL` — pulls an unassigned key from a pre-generated batch
    (e.g. PayPal webhook → pull a key → email it)
  - `ON_DEMAND` — generates a fresh key at issuance time, with
    automatic retry on the (extremely rare) collision
- **Trial tracking is a separate table from the license itself** —
  a license can outlive its trial (e.g. customer upgrades from trial
  to paid; same key, the trial row just stops being checked)
- **Configurable trial limits per issuance** — time-based only,
  run-count only, both (KerfCut's 30-day/20-run model), or neither
- **Optional machine-binding** — the column always exists, but stays
  `null`/unused for products that don't need it. Binding is never
  automatic — you call `bind_machine()` explicitly after a
  successful first validation, so it's a deliberate step, not a side
  effect of checking
- **Atomic pool claiming** — same atomic-claim pattern as
  `synon_scheduler`, so two simultaneous issuances (e.g. two webhooks
  landing the same second) can never grab the same pooled key
- **Structured validation results** — `validate_license()` returns a
  specific reason (`TRIAL_EXPIRED`, `MACHINE_MISMATCH`,
  `TRIAL_RUNS_EXHAUSTED`, etc.), not just valid/invalid, so your UI
  can show the right message

## What it deliberately does NOT do

- Send the license key to the customer — that's your notifications
  module's job (Resend, etc.); this module just issues and returns
  the key
- Handle payment — that's `synon_webhooks`' job (verify the PayPal/
  Paddle event), which calls into this module's `issue_license()`
  once payment is confirmed
- Auto-bind machines on first check — binding is explicit, see above

## Setup

1. Copy this folder into your project.
2. Run `schema.sql` against your Supabase instance (creates all
   three tables AND the `claim_pool_key` Postgres function).
3. Copy `.env.example` values into your `.env`.
4. `pip install -r requirements.txt`.

## Issuing a license — pool mode

For products that pre-generate a batch of keys (KerfCut's pattern):

```python
from synon_licensing import LicensingStore, LicenseSource

store = LicensingStore()

# One-time (or whenever you need to top up): generate a batch
store.add_to_pool(product="kerfcut", count=100)

# At purchase time (e.g. inside your synon_webhooks PayPal handler):
license = store.issue_license(
    product="kerfcut",
    source=LicenseSource.POOL,
    customer_email="customer@example.com",
)
print(license.key)  # hand this to your notifications module
```

## Issuing a license — on-demand mode

For products with no pre-generated pool:

```python
license = store.issue_license(
    product="kerfstock",
    source=LicenseSource.ON_DEMAND,
    customer_email="customer@example.com",
)
```

## Starting a trial (KerfCut-style: 30 days OR 20 runs, whichever first)

```python
store.start_trial(license.id, max_days=30, max_runs=20)
```

Pass `max_days=None` for a runs-only trial, or `max_runs=None` for a
time-only trial. Pass neither (skip `start_trial` entirely) for a
license with no trial constraints at all.

## Validating a license (called on app startup)

```python
from synon_licensing import validate_license, LicenseCheckResult

outcome = validate_license(
    store=store,
    key=user_entered_key,       # normalize first — see below
    product="kerfcut",
    machine_id=this_machines_id,  # None if product doesn't bind machines
    consume_run=True,            # True if this is an actual run, False for a status check
)

if outcome.is_valid:
    # let the app run
    ...
elif outcome.result == LicenseCheckResult.TRIAL_EXPIRED:
    show_message("Your trial has ended. Purchase a license to continue.")
elif outcome.result == LicenseCheckResult.TRIAL_RUNS_EXHAUSTED:
    show_message("You've used all your trial runs.")
elif outcome.result == LicenseCheckResult.MACHINE_MISMATCH:
    show_message("This key is already bound to a different machine.")
else:
    show_message("Invalid license key.")
```

## Normalizing customer input

Always normalize before validating — customers paste keys with
inconsistent casing/whitespace:

```python
from synon_licensing import normalize_key_input

key = normalize_key_input(raw_input_from_user)
outcome = validate_license(store, key, "kerfcut")
```

## Binding a machine (explicit, after first successful validation)

```python
outcome = validate_license(store, key, "kerfcut", machine_id=this_machine_id)
if outcome.is_valid and outcome.license_key.bound_machine_id is None:
    store.bind_machine(outcome.license_key, this_machine_id)
```

## Revoking a license

```python
license = store.get_license(key)
store.revoke(license)
```

## Files

| File | Purpose |
|---|---|
| `config.py` | Env-driven settings (ALL_CAPS_SNAKE) |
| `models.py` | `LicenseKey`, `TrialUsage`, result enums |
| `keygen.py` | Pure key generation + input normalization |
| `store.py` | Supabase-backed persistence, pool, issuance |
| `validator.py` | `validate_license()` — the core check |
| `schema.sql` | Supabase tables + atomic `claim_pool_key()` function |

## Known untested piece

The `claim_pool_key()` Postgres function in `schema.sql` has not been
executed against a real database (no local Postgres available in the
build environment). Test it directly in the Supabase SQL editor
before wiring up the Python side — add a couple of dummy pool rows,
call `select * from claim_pool_key('license_key_pool', 'test_product')`,
and confirm it returns a key and marks the row `assigned = true`.
