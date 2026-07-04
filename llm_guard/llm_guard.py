"""
synon_llm_guard
-----------------
Deterministic, rule-based defense layer for LLM-powered features:

1. InjectionGuard - scores incoming text for prompt-injection risk before
   it ever reaches your context assembler / LLM call.
2. PiiScrubber - detects and redacts PII (emails, phone numbers, card
   numbers, API keys, etc.) - use on OUTPUT before it reaches the user,
   and optionally on input before it reaches the LLM / gets logged.

No ML model, no external API calls, no dependencies beyond stdlib `re`.
This won't catch everything a determined attacker throws at it (nothing
regex-based will), but it's a fast, free, zero-latency first line of
defense that catches the common/lazy attempts and PII leakage before
paying for a heavier check.

Usage:
    from llm_guard import LLMGuard

    guard = LLMGuard()

    result = guard.check_input(user_message)
    if result.decision == "block":
        # reject before calling the LLM at all
        ...

    reply = call_llm(...)
    scrub_result = guard.scrub_output(reply)
    safe_reply = scrub_result.clean_text
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Literal

from patterns import INJECTION_PATTERNS, PII_PATTERNS

Decision = Literal["allow", "flag", "block"]


def _float_env(name: str, default: float) -> float:
    val = os.getenv(name)
    return float(val) if val else default


FLAG_THRESHOLD = _float_env("INJECTION_FLAG_THRESHOLD", 0.3)
BLOCK_THRESHOLD = _float_env("INJECTION_BLOCK_THRESHOLD", 0.7)
PII_MODE = os.getenv("PII_MODE", "redact")  # "redact" | "flag_only"


@dataclass
class GuardResult:
    decision: Decision
    score: float
    matched_patterns: List[str] = field(default_factory=list)


@dataclass
class ScrubResult:
    clean_text: str
    redactions: Dict[str, int] = field(default_factory=dict)  # {"EMAIL": 2, "API_KEY": 1, ...}

    @property
    def had_pii(self) -> bool:
        return len(self.redactions) > 0


class InjectionGuard:
    def __init__(self, flag_threshold: float = FLAG_THRESHOLD, block_threshold: float = BLOCK_THRESHOLD):
        self.flag_threshold = flag_threshold
        self.block_threshold = block_threshold

    def check(self, text: str) -> GuardResult:
        if not text:
            return GuardResult(decision="allow", score=0.0)

        score = 0.0
        matched: List[str] = []
        for pattern, weight in INJECTION_PATTERNS:
            if pattern.search(text):
                score += weight
                matched.append(pattern.pattern)

        score = min(score, 1.0)

        if score >= self.block_threshold:
            decision: Decision = "block"
        elif score >= self.flag_threshold:
            decision = "flag"
        else:
            decision = "allow"

        return GuardResult(decision=decision, score=round(score, 3), matched_patterns=matched)


class PiiScrubber:
    def __init__(self, mode: str = PII_MODE):
        self.mode = mode  # "redact" replaces matches, "flag_only" leaves text untouched

    def scrub(self, text: str) -> ScrubResult:
        if not text:
            return ScrubResult(clean_text=text or "")

        redactions: Dict[str, int] = {}
        clean_text = text

        for label, pattern in PII_PATTERNS.items():
            matches = pattern.findall(clean_text)
            if not matches:
                continue
            count = len(pattern.findall(clean_text))
            redactions[label] = count
            if self.mode == "redact":
                clean_text = pattern.sub(f"[REDACTED_{label}]", clean_text)

        return ScrubResult(clean_text=clean_text, redactions=redactions)


class LLMGuard:
    """Convenience wrapper combining both checks."""

    def __init__(self, injection_guard: InjectionGuard = None, pii_scrubber: PiiScrubber = None):
        self.injection_guard = injection_guard or InjectionGuard()
        self.pii_scrubber = pii_scrubber or PiiScrubber()

    def check_input(self, text: str) -> GuardResult:
        """Run before the text reaches your context assembler / LLM call."""
        return self.injection_guard.check(text)

    def scrub_output(self, text: str) -> ScrubResult:
        """Run on the LLM's reply before it reaches the user or gets logged."""
        return self.pii_scrubber.scrub(text)

    def scrub_input(self, text: str) -> ScrubResult:
        """Optional: scrub PII out of user input before it hits the LLM/context/logs."""
        return self.pii_scrubber.scrub(text)
