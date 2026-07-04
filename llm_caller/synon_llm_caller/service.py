import json
import requests
from typing import Optional

from .config import LLMCallerConfig


class LLMCallerService:
    def __init__(self, config: LLMCallerConfig):
        self.config = config

    def call(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Sends a single prompt to the configured LLM endpoint and returns the
        text of the reply.
        """
        if not self.config.api_key:
            raise RuntimeError("LLM_API_KEY is not set.")

        try:
            response = requests.post(
                self.config.api_url,
                headers=self._build_headers(),
                json=self._build_payload(prompt, system),
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"LLM request failed: {e}") from e

        data = response.json()

        # Anthropic-style response parsing by default
        try:
            text_blocks = [
                block["text"] for block in data.get("content", [])
                if block.get("type") == "text"
            ]
            return "\n".join(text_blocks).strip()
        except (KeyError, TypeError) as e:
            raise RuntimeError(f"Unexpected response shape: {json.dumps(data)[:500]}") from e

    def _build_headers(self) -> dict:
        # Default to Anthropic headers
        return {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
            "anthropic-version": self.config.anthropic_version,
        }

    def _build_payload(self, prompt: str, system: Optional[str] = None) -> dict:
        payload = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        return payload
