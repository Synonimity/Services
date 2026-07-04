"""
synon_fallback_router
-----------------------
Tries multiple LLM providers in priority order, retrying with backoff
within a provider before giving up and falling back to the next one.
Built for a multi-LLM setup (Claude, Gemini, GPT, Groq, DeepSeek, etc.) -
providers.py has builder helpers for Anthropic-style and OpenAI-compatible
endpoints, but a Provider is really just "a name + a zero-arg callable
that returns a string or raises" - wrap anything, including your own
call_fn from llm_caller.py.

Usage:
    from fallback_router import FallbackRouter, Provider

    router = FallbackRouter(providers=[
        Provider(name="claude", call_fn=lambda: call_claude(prompt)),
        Provider(name="gpt",    call_fn=lambda: call_gpt(prompt)),
        Provider(name="groq",   call_fn=lambda: call_groq(prompt)),
    ])

    result = router.call()
    print(result.output, result.provider_name, result.attempts_used)
"""

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple, Any


@dataclass
class Provider:
    name: str
    call_fn: Callable[[], Any]
    max_retries: int = 1                 # retries WITHIN this provider before falling back
    backoff_base: float = 0.5            # seconds; actual wait = backoff_base * 2**attempt
    retryable_exceptions: Tuple = (Exception,)


@dataclass
class ProviderError:
    provider: str
    attempt: int
    error: str


@dataclass
class RouterResult:
    success: bool
    output: Any = None
    provider_name: Optional[str] = None
    attempts_used: int = 0
    errors: List[ProviderError] = field(default_factory=list)


class AllProvidersFailedError(Exception):
    def __init__(self, errors: List[ProviderError]):
        self.errors = errors
        summary = "; ".join(f"{e.provider} (attempt {e.attempt}): {e.error}" for e in errors)
        super().__init__(f"All providers failed. {summary}")


class FallbackRouter:
    def __init__(self, providers: List[Provider]):
        if not providers:
            raise ValueError("FallbackRouter needs at least one provider.")
        self.providers = providers

    def call(self) -> RouterResult:
        """
        Tries each provider in order. Within a provider, retries up to
        max_retries times with exponential backoff before moving to the
        next provider. Returns on first success; raises
        AllProvidersFailedError if every provider is exhausted.
        """
        errors: List[ProviderError] = []
        total_attempts = 0

        for provider in self.providers:
            for attempt in range(1, provider.max_retries + 1):
                total_attempts += 1
                try:
                    output = provider.call_fn()
                    return RouterResult(
                        success=True, output=output, provider_name=provider.name,
                        attempts_used=total_attempts, errors=errors,
                    )
                except provider.retryable_exceptions as e:
                    errors.append(ProviderError(provider=provider.name, attempt=attempt, error=str(e)))
                    if attempt < provider.max_retries:
                        wait = provider.backoff_base * (2 ** (attempt - 1))
                        time.sleep(wait)
                    # else: exhausted retries for this provider, fall through to next provider

        raise AllProvidersFailedError(errors)

    def call_safe(self) -> RouterResult:
        """Same as call(), but returns a failed RouterResult instead of raising."""
        try:
            return self.call()
        except AllProvidersFailedError as e:
            return RouterResult(success=False, errors=e.errors, attempts_used=len(e.errors))
