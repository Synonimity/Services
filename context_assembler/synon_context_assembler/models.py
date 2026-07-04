from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ContextSource:
    id: str
    text: str
    priority: int = 1
    pinned: bool = False
    role: str = "user"
    estimated_tokens: int = 0


@dataclass
class AssemblyResult:
    text: str
    total_tokens: int
    dropped: List[str] = field(default_factory=list)
    truncated: List[str] = field(default_factory=list)
    sources_used: List[ContextSource] = field(default_factory=list)

    def as_messages(self) -> List[Dict[str, str]]:
        """Format as a list of message objects for llm_caller."""
        return [{"role": s.role, "content": s.text} for s in self.sources_used]
