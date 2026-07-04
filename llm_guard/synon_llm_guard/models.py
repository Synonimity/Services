from dataclasses import dataclass, field
from typing import List, Dict, Literal

Decision = Literal["allow", "flag", "block"]


@dataclass
class GuardResult:
    decision: Decision
    score: float
    matched_patterns: List[str] = field(default_factory=list)


@dataclass
class ScrubResult:
    clean_text: str
    redactions: Dict[str, int] = field(default_factory=dict)

    @property
    def had_pii(self) -> bool:
        return len(self.redactions) > 0
