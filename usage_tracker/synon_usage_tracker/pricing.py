"""
Model pricing table for synon_usage_tracker.

Prices are USD per 1,000,000 tokens (the common convention for LLM
pricing pages) so numbers are human-readable at a glance. Kept separate
from the tracking logic so you can update prices or add models without
touching anything else.

Unknown models fall back to DEFAULT_PRICING rather than raising - better
to under/over-estimate slightly than to crash a request over a pricing
table that's gone stale.
"""

# USD per 1,000,000 tokens: {"input": ..., "output": ...}
MODEL_PRICING = {
    "claude-opus-4-8":  {"input": 15.00, "output": 75.00},
    "claude-sonnet-5":  {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
}

DEFAULT_PRICING = {"input": 3.00, "output": 15.00}

TOKENS_PER_UNIT = 1_000_000


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
    input_cost = (input_tokens / TOKENS_PER_UNIT) * pricing["input"]
    output_cost = (output_tokens / TOKENS_PER_UNIT) * pricing["output"]
    return round(input_cost + output_cost, 6)
