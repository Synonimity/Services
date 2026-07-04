"""
synon_usage_tracker
---------------------
Tracks per-user token usage + cost, and enforces plan quotas. Ties into
the licensing/ratelimit pattern already established elsewhere in the
library - this module owns "how much has this user used and are they
over their limit," nothing more.

Usage:
    from usage_tracker import UsageTracker
    from backends import InMemoryBackend

    tracker = UsageTracker(backend=InMemoryBackend())

    # After every LLM call:
    event = tracker.record(user_id="user_123", model="claude-sonnet-5",
                            input_tokens=850, output_tokens=412)

    # Before allowing a new request:
    quota = tracker.check_quota(user_id="user_123", plan="trial")
    if not quota.within_limit:
        raise Exception(f"Quota exceeded: {quota.reason}")
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from calendar import monthrange
from typing import Optional, Dict, List

from pricing import estimate_cost
from plans import PLAN_LIMITS, DEFAULT_PLAN


@dataclass
class UsageEvent:
    user_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    created_at: datetime
    session_id: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "created_at": self.created_at,
        }


@dataclass
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    event_count: int = 0


@dataclass
class QuotaResult:
    within_limit: bool
    used_tokens: int
    used_cost: float
    max_tokens: Optional[int]
    max_cost: Optional[float]
    period_start: datetime
    reason: Optional[str] = None


def _period_start(period: str, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # "all" / unrecognized -> epoch, effectively no lower bound
    return datetime.min.replace(tzinfo=timezone.utc)


class UsageTracker:
    def __init__(self, backend, plan_limits: Dict[str, dict] = None):
        self.backend = backend
        self.plan_limits = plan_limits or PLAN_LIMITS

    def record(
        self,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
    ) -> UsageEvent:
        cost = estimate_cost(model, input_tokens, output_tokens)
        event = UsageEvent(
            user_id=user_id, model=model, input_tokens=input_tokens,
            output_tokens=output_tokens, cost=cost,
            created_at=datetime.now(timezone.utc), session_id=session_id,
        )
        self.backend.log_event(event.as_dict())
        return event

    def get_totals(self, user_id: str, period: str = "all", now: Optional[datetime] = None) -> UsageTotals:
        since = _period_start(period, now) if period != "all" else None
        events = self.backend.get_events(user_id, since=since)

        totals = UsageTotals()
        for e in events:
            totals.input_tokens += e["input_tokens"]
            totals.output_tokens += e["output_tokens"]
            totals.cost += e["cost"]
            totals.event_count += 1
        totals.total_tokens = totals.input_tokens + totals.output_tokens
        totals.cost = round(totals.cost, 6)
        return totals

    def check_quota(self, user_id: str, plan: str = DEFAULT_PLAN, now: Optional[datetime] = None) -> QuotaResult:
        plan_config = self.plan_limits.get(plan)
        if plan_config is None:
            raise ValueError(f"Unknown plan '{plan}'. Known plans: {list(self.plan_limits.keys())}")

        period = plan_config.get("period", "month")
        max_tokens = plan_config.get("max_tokens_per_period")
        max_cost = plan_config.get("max_cost_per_period")

        totals = self.get_totals(user_id, period=period, now=now)
        period_start = _period_start(period, now)

        if max_tokens is not None and totals.total_tokens >= max_tokens:
            return QuotaResult(
                within_limit=False, used_tokens=totals.total_tokens, used_cost=totals.cost,
                max_tokens=max_tokens, max_cost=max_cost, period_start=period_start,
                reason=f"Token quota exceeded: {totals.total_tokens}/{max_tokens} this {period}.",
            )

        if max_cost is not None and totals.cost >= max_cost:
            return QuotaResult(
                within_limit=False, used_tokens=totals.total_tokens, used_cost=totals.cost,
                max_tokens=max_tokens, max_cost=max_cost, period_start=period_start,
                reason=f"Cost quota exceeded: ${totals.cost:.4f}/${max_cost:.2f} this {period}.",
            )

        return QuotaResult(
            within_limit=True, used_tokens=totals.total_tokens, used_cost=totals.cost,
            max_tokens=max_tokens, max_cost=max_cost, period_start=period_start,
        )
