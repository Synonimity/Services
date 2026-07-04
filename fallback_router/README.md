# synon_fallback_router

Tries multiple LLM providers in priority order. Retries within a provider
(with exponential backoff) before falling back to the next one. Built for
a multi-LLM setup — Claude, GPT, Groq, DeepSeek, whatever you've got keys
for — so a single provider outage or rate limit doesn't take your whole
AI feature down.

A `Provider` is just a name + a zero-arg callable that returns a string
or raises. `providers.py` has builder helpers for the two dominant API
shapes (Anthropic-style, OpenAI-compatible), but you can wrap literally
anything, including your own `call_llm()` from `llm_caller.py`.

## Quick start — using the builder helpers

```python
from fallback_router import FallbackRouter, Provider
from providers import make_anthropic_call_fn, make_openai_compatible_call_fn

prompt = "Summarize this ticket for a support agent."

router = FallbackRouter(providers=[
    Provider(
        name="claude",
        call_fn=make_anthropic_call_fn(prompt, api_key_env="ANTHROPIC_API_KEY", model="claude-sonnet-5"),
        max_retries=2,
    ),
    Provider(
        name="groq",
        call_fn=make_openai_compatible_call_fn(
            prompt, api_key_env="GROQ_API_KEY", model="llama-3.3-70b-versatile",
            api_url="https://api.groq.com/openai/v1/chat/completions",
        ),
        max_retries=2,
    ),
])

result = router.call()
print(result.output, "from", result.provider_name, "in", result.attempts_used, "attempts")
```

## Quick start — wrapping your own call_fn

```python
from fallback_router import FallbackRouter, Provider
from llm_caller import call_llm   # your existing microservice

router = FallbackRouter(providers=[
    Provider(name="primary", call_fn=lambda: call_llm(prompt), max_retries=2),
    Provider(name="backup",  call_fn=lambda: call_backup_llm(prompt), max_retries=1),
])

result = router.call()
```

## Behavior

- Tries providers **in list order**. Within a provider, retries up to
  `max_retries` times with backoff (`backoff_base * 2**attempt`,
  default `0.5s, 1s, 2s...`) before moving to the next provider.
- `call()` returns a `RouterResult` on success (`output`, `provider_name`,
  `attempts_used`, and the list of errors from any providers that failed
  along the way) or raises `AllProvidersFailedError` if every provider is
  exhausted.
- `call_safe()` is the same thing but returns a failed `RouterResult`
  instead of raising — use it if you'd rather check `result.success` than
  wrap in try/except.
- `retryable_exceptions` on a `Provider` lets you control what counts as
  "worth retrying" vs. "fail immediately and move to the next provider"
  (e.g. don't retry on a 401 auth error, do retry on a timeout/429).

## Notes

- Order your provider list by preference/cost/quality — first provider
  that works wins, nothing fancy about ranking after that.
- `Provider.call_fn` is evaluated fresh on every attempt (it's a
  callable, not a cached value), so each retry is a real new request.
- This doesn't do quality comparison between providers — it's pure
  failover, not "pick the best answer." If you need that, that's a
  different (and much more expensive) tool.
