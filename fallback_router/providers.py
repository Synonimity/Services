"""
Builder helpers that turn provider config into the zero-arg callables
FallbackRouter expects. Covers the two dominant API shapes:

- Anthropic-style: x-api-key header, {"content": [{"type": "text", ...}]} response
- OpenAI-compatible: Bearer token, {"choices": [{"message": {"content": ...}}]}
  response - this covers OpenAI itself plus most OpenAI-compatible APIs
  (Groq, DeepSeek, many local/self-hosted endpoints).

These are just convenience builders. A Provider only needs a name and a
zero-arg callable - if a provider doesn't fit either shape, write your own
call_fn and skip these helpers entirely.
"""

import os
import requests
from typing import Optional


def anthropic_provider_call(
    prompt: str,
    api_key: str,
    model: str,
    system: Optional[str] = None,
    api_url: str = "https://api.anthropic.com/v1/messages",
    max_tokens: int = 1000,
    timeout: int = 60,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    return "\n".join(blocks).strip()


def openai_compatible_provider_call(
    prompt: str,
    api_key: str,
    model: str,
    system: Optional[str] = None,
    api_url: str = "https://api.openai.com/v1/chat/completions",
    max_tokens: int = 1000,
    timeout: int = 60,
) -> str:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {"model": model, "max_tokens": max_tokens, "messages": messages}

    resp = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def make_anthropic_call_fn(prompt: str, api_key_env: str, model: str, system: Optional[str] = None, **kwargs):
    """Returns a zero-arg callable, ready to hand to a Provider."""
    api_key = os.getenv(api_key_env)
    return lambda: anthropic_provider_call(prompt, api_key=api_key, model=model, system=system, **kwargs)


def make_openai_compatible_call_fn(prompt: str, api_key_env: str, model: str, system: Optional[str] = None, **kwargs):
    """Returns a zero-arg callable. Works for OpenAI, Groq, DeepSeek, etc. - anything OpenAI-schema-compatible."""
    api_key = os.getenv(api_key_env)
    return lambda: openai_compatible_provider_call(prompt, api_key=api_key, model=model, system=system, **kwargs)
