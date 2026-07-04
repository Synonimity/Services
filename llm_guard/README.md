# synon_llm_guard

Deterministic, rule-based security layer for LLM-powered features. Two jobs:

1. **InjectionGuard** — scores incoming text for prompt-injection risk
   *before* it reaches your context assembler or the LLM.
2. **PiiScrubber** — detects and redacts PII (emails, phone numbers, card
   numbers, API keys, AWS keys, etc.) — use on the LLM's *output* before
   it reaches the user, and optionally on input before it hits the LLM or
   your logs.

No ML model, no external calls, no dependencies beyond stdlib `re`. This
is a fast, free, zero-latency first line of defense — it catches common
and lazy attempts, not everything a determined attacker will throw at it.
Layer it in front of something heavier if your threat model needs that.

## Quick start

```python
from llm_guard import LLMGuard

guard = LLMGuard()

# 1. Check input BEFORE it reaches context_assembler / llm_caller
result = guard.check_input(user_message)
if result.decision == "block":
    return "I can't process that request."
elif result.decision == "flag":
    log_for_review(user_message, result.score, result.matched_patterns)
    # still allowed through, just logged

# 2. ... assemble context, call the LLM ...
reply = call_llm(assembled_context)

# 3. Scrub PII out of the reply before it reaches the user
scrub_result = guard.scrub_output(reply)
safe_reply = scrub_result.clean_text
if scrub_result.had_pii:
    log_pii_leak(scrub_result.redactions)  # e.g. {"EMAIL": 1}
```

## Decision thresholds

Score is a sum of matched pattern weights, capped at 1.0.

| Score range | Decision |
|---|---|
| `< INJECTION_FLAG_THRESHOLD` (default 0.3) | `allow` |
| `>= FLAG` and `< BLOCK` | `flag` — let it through, but log it |
| `>= INJECTION_BLOCK_THRESHOLD` (default 0.7) | `block` |

Tune both in `.env`. Everything is env-driven with safe defaults baked in
if you don't set anything.

## PII types detected

`EMAIL`, `PHONE`, `CREDIT_CARD`, `SSN_US`, `IPV4`, `API_KEY` (generic
`sk-`/`key-`/`bearer` style tokens), `AWS_KEY`.

Set `PII_MODE=flag_only` in `.env` if you want detection/reporting without
mutating the text (e.g. for audit logging alongside the original).

## Extending

All patterns live in `patterns.py`, separate from the scoring logic in
`llm_guard.py`. Add new injection patterns or PII regexes there — weights
are subjective starting points, tune them against your own attack/false-
positive samples over time. Nothing else needs to change.

## Known limitations

- Regex-based injection detection will miss cleverly obfuscated or
  novel attacks (e.g. base64-encoded instructions, unusual phrasing).
  Treat `flag` as "worth a second look," not proof of malice.
- `CREDIT_CARD` and `PHONE` patterns are loose on purpose to catch more
  formats — expect some false positives on long numeric strings.
- No Luhn check on credit cards; it's a shape match, not a validity check.
