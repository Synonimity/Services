"""
synon_licensing.keygen

Pure key-generation logic — no database, no IO, easy to test in
isolation. Format: XXXX-XXXX-XXXX-XXXX by default (configurable
segment count/length via config.py).

Uses an unambiguous alphabet (no 0/O, 1/I/L) so a customer reading a
key aloud over the phone or typing it manually doesn't get tripped up
by lookalike characters.
"""

import secrets

from . import config

# Excludes: 0, O, 1, I, L — and lowercase entirely (keys are generated
# uppercase; if you display/accept lowercase input, normalize with
# .upper() before comparing, don't add lowercase to this alphabet)
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_key_string(
    segment_count: int = None,
    segment_length: int = None,
) -> str:
    """
    Generates a single key string, e.g. "K7XJ-2MNP-9QRT-VWYZ".
    Does NOT check uniqueness against the database — that's the
    caller's job (retry on unique-constraint violation, or check
    before insert).
    """
    segment_count = segment_count or config.LICENSE_KEY_SEGMENT_COUNT
    segment_length = segment_length or config.LICENSE_KEY_SEGMENT_LENGTH

    segments = [
        "".join(secrets.choice(_ALPHABET) for _ in range(segment_length))
        for _ in range(segment_count)
    ]
    return "-".join(segments)


def normalize_key_input(raw: str) -> str:
    """
    Normalize a customer-typed key before lookup: uppercase, strip
    whitespace. Doesn't try to be clever about correcting typos —
    that's a UX decision for the calling app, not this library.
    """
    return raw.strip().upper()
