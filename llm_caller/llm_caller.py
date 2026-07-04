"""
synon_llmcaller
----------------
Minimal microservice for calling an LLM API. Provider/model/endpoint are
all configurable via .env so this same script can point at Anthropic,
OpenAI-compatible, or any other Bearer-token JSON API without code changes.

Usage:
    from llm_caller import call_llm
    reply = call_llm("Say hello in one sentence.")

    # or run directly:
    python llm_caller.py "Say hello in one sentence."
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL", "https://api.anthropic.com/v1/messages")
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "60"))

# Anthropic-style headers by default. If you point this at a different
# provider (OpenAI-compatible, etc.), swap the header block below.
def _build_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }


def _build_payload(prompt: str, system: str | None = None) -> dict:
    payload = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    return payload


def call_llm(prompt: str, system: str | None = None) -> str:
    """
    Sends a single prompt to the configured LLM endpoint and returns the
    text of the reply. Raises RuntimeError on any failure.
    """
    if not API_KEY:
        raise RuntimeError("API_KEY is not set. Check your .env file.")

    try:
        response = requests.post(
            API_URL,
            headers=_build_headers(),
            json=_build_payload(prompt, system),
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"LLM request failed: {e}") from e

    data = response.json()

    # Anthropic-style response parsing
    try:
        text_blocks = [
            block["text"] for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        return "\n".join(text_blocks).strip()
    except (KeyError, TypeError) as e:
        raise RuntimeError(f"Unexpected response shape: {json.dumps(data)[:500]}") from e


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python llm_caller.py \"your prompt here\"")
        sys.exit(1)

    user_prompt = " ".join(sys.argv[1:])
    try:
        result = call_llm(user_prompt)
        print(result)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
