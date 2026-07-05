from datetime import datetime, timezone
from typing import Optional, Dict

from .models import UsageEvent, UsageTotals, QuotaResult
from .pricing import estimate_cost
from .plans import PLAN_LIMITS
from .config import UsageTrackerConfig


def _period_start(period: str, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if period == "day":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return datetime.min.replace(tzinfo=timezone.utc)


class UsageTrackerService:
    def __init__(self, config: UsageTrackerConfig, backend, plan_limits: Optional[Dict[str, dict]] = None):
        self.config = config
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

    def check_quota(self, user_id: str, plan: Optional[str] = None, now: Optional[datetime] = None) -> QuotaResult:
        plan_name = plan or self.config.default_plan
        plan_config = self.plan_limits.get(plan_name)
        if plan_config is None:
            raise ValueError(f"Unknown plan '{plan_name}'. Known plans: {list(self.plan_limits.keys())}")

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
