"""
Pattern libraries for synon_llm_guard.

Kept separate from the scoring logic so you can extend/tune these lists
without touching the algorithm. Weights are subjective starting points -
tune against your own attack samples over time.
"""

import re

# ---------------------------------------------------------------------------
# Prompt injection patterns
# Each entry: (compiled regex, weight). Weights sum into a 0-1+ risk score.
# ---------------------------------------------------------------------------

_RAW_INJECTION_PATTERNS = [
    # Direct override attempts
    (r"\bignore (all |any )?(previous|prior|above|earlier) (instructions?|prompts?|rules?)\b", 0.4),
    (r"\bdisregard (all |any )?(previous|prior|above|earlier)\b", 0.4),
    (r"\bforget (everything|all|your instructions|what (i|you) (said|told))\b", 0.35),
    (r"\byou (are|'re) now\b.{0,40}\b(dan|jailbroken|unrestricted|uncensored)\b", 0.5),
    (r"\bdeveloper mode\b", 0.3),
    (r"\bsystem prompt\b.{0,30}\b(reveal|show|print|repeat|leak)\b", 0.4),
    (r"\b(reveal|show|print|output|repeat) (your |the )?(system prompt|instructions|rules)\b", 0.4),
    (r"\bact as (if you were|though you (are|were))\b", 0.2),
    (r"\bpretend (you have no|there are no) (restrictions|rules|guidelines)\b", 0.4),
    (r"\bnew instructions?:?\s*$", 0.25),
    (r"\bend of (system prompt|instructions)\b", 0.35),
    (r"\[\s*system\s*\]", 0.2),
    (r"</?\s*(system|instructions|admin)\s*>", 0.3),
    # Delimiter / structure-breaking attempts
    (r"-{3,}\s*(end|begin)\s*(system|prompt|instructions)", 0.35),
    (r"```\s*(system|instructions)\b", 0.25),
    # Exfiltration attempts
    (r"\brepeat (the )?(words|text) above\b", 0.35),
    (r"\boutput (everything|all text) (above|before) this\b", 0.35),
]

INJECTION_PATTERNS = [(re.compile(p, re.IGNORECASE), w) for p, w in _RAW_INJECTION_PATTERNS]


# ---------------------------------------------------------------------------
# PII patterns
# Each entry: (label, compiled regex)
# ---------------------------------------------------------------------------

PII_PATTERNS = {
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE": re.compile(r"\b(\+?\d{1,3}[\s.-]?)?(\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "SSN_US": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "IPV4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "API_KEY": re.compile(r"\b(sk|pk|key|api|bearer)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE),
    "AWS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
