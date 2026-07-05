from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


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
