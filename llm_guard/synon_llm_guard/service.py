from .config import LLMGuardConfig
from .models import GuardResult, ScrubResult, Decision
from .patterns import INJECTION_PATTERNS, PII_PATTERNS


class InjectionGuard:
    def __init__(self, config: LLMGuardConfig):
        self.config = config

    def check(self, text: str) -> GuardResult:
        if not text:
            return GuardResult(decision="allow", score=0.0)

        score = 0.0
        matched = []
        for pattern, weight in INJECTION_PATTERNS:
            if pattern.search(text):
                score += weight
                matched.append(pattern.pattern)

        score = min(score, 1.0)

        if score >= self.config.injection_block_threshold:
            decision: Decision = "block"
        elif score >= self.config.injection_flag_threshold:
            decision = "flag"
        else:
            decision = "allow"

        return GuardResult(decision=decision, score=round(score, 3), matched_patterns=matched)


class PiiScrubber:
    def __init__(self, config: LLMGuardConfig):
        self.config = config

    def scrub(self, text: str) -> ScrubResult:
        if not text:
            return ScrubResult(clean_text=text or "")

        redactions = {}
        clean_text = text

        for label, pattern in PII_PATTERNS.items():
            matches = pattern.findall(clean_text)
            if not matches:
                continue
            redactions[label] = len(matches)
            if self.config.pii_mode == "redact":
                clean_text = pattern.sub(f"[REDACTED_{label}]", clean_text)

        return ScrubResult(clean_text=clean_text, redactions=redactions)


class LLMGuardService:
    """Convenience service combining injection guard and PII scrubber."""
    def __init__(self, config: LLMGuardConfig):
        self.injection_guard = InjectionGuard(config)
        self.pii_scrubber = PiiScrubber(config)

    def check_input(self, text: str) -> GuardResult:
        return self.injection_guard.check(text)

    def scrub_output(self, text: str) -> ScrubResult:
        return self.pii_scrubber.scrub(text)

    def scrub_input(self, text: str) -> ScrubResult:
        return self.pii_scrubber.scrub(text)
