"""
Plan/quota definitions for synon_usage_tracker.

Deliberately simple dict config, consistent with KerfSuite's licensing
model (fixed trial window, no free tier). Extend with more plans/limits
as needed - the tracker doesn't care how many you define.

A limit of None means "unlimited" for that dimension.
"""

PLAN_LIMITS = {
    "trial": {"max_tokens_per_period": 200_000, "max_cost_per_period": None, "period": "month"},
    "pro":   {"max_tokens_per_period": None,     "max_cost_per_period": 50.00, "period": "month"},
    "unlimited": {"max_tokens_per_period": None, "max_cost_per_period": None, "period": "month"},
}

DEFAULT_PLAN = "trial"
