"""
Groups error occurrences that are "the same bug" even when the message
contains different dynamic data each time (a different user ID, a
different filename, etc.) - the same idea Sentry/Rollbar use, simplified.

This is a heuristic, not a guarantee. It's intentionally language-agnostic
(works for Python, JS, Go, whatever) rather than parsing stack frames,
which differ wildly in format between languages. If the default grouping
is too aggressive or too loose for a particular error, pass
`fingerprint_override` in the report and skip this entirely.
"""
import hashlib
import re

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_HEX_ADDR_RE = re.compile(r"0x[0-9a-f]{4,}", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d+")
_QUOTED_RE = re.compile(r"(['\"]).*?\1")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_message(message: str) -> str:
    text = message.lower()
    text = _UUID_RE.sub("<uuid>", text)
    text = _HEX_ADDR_RE.sub("<hex>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _NUMBER_RE.sub("<num>", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    # Cap length - extremely long messages (e.g. a dumped payload) shouldn't
    # blow up grouping granularity or storage.
    return text[:500]


def compute_fingerprint(*, service_name: str, environment: str, exception_type: str, message: str) -> str:
    normalized = normalize_message(message)
    raw = f"{service_name}:{environment}:{exception_type}:{normalized}"
    return hashlib.sha256(raw.encode()).hexdigest()
