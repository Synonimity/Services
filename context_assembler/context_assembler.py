"""
synon_context_assembler
------------------------
Deterministic algorithm for assembling an LLM context window from multiple
pieces (system prompt, user facts, conversation history, RAG snippets, the
current message) and trimming them to fit a token budget.

This is NOT an LLM call. It decides *what* goes into the prompt before
llm_caller.py (or equivalent) ever sends anything. Pure, deterministic,
testable.

Core idea:
- Every piece of context is a ContextSource with a priority and a position.
- PINNED sources (e.g. system prompt, current user message) are always
  included in full and are never trimmed or dropped.
- Non-pinned sources are selected by priority (highest first) until the
  token budget runs out. A source that partially fits gets truncated;
  anything that doesn't fit at all is dropped.
- Final output preserves original POSITION order (not priority order) so
  the assembled context still reads naturally: system -> facts -> history
  -> current message.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Literal

TOKEN_CHARS_PER_TOKEN = 4  # crude fallback heuristic: ~4 chars per token

TruncateFrom = Literal["start", "end"]


def estimate_tokens(text: str) -> int:
    """
    Cheap, dependency-free token estimate. Swap this out for a real
    tokenizer (tiktoken, anthropic's counter, etc.) if you need precision -
    the rest of the algorithm doesn't care how tokens are counted.
    """
    if not text:
        return 0
    return max(1, len(text) // TOKEN_CHARS_PER_TOKEN)


@dataclass
class ContextSource:
    name: str
    content: str
    priority: int = 5          # higher = kept first when trimming
    pinned: bool = False       # pinned sources are never trimmed/dropped
    position: int = 0          # controls final output order
    role: str = "system"       # "system" | "user" | "assistant"
    truncate_from: TruncateFrom = "start"  # which end to cut when trimming
    token_estimate: Optional[int] = None

    def tokens(self) -> int:
        return self.token_estimate if self.token_estimate is not None else estimate_tokens(self.content)


@dataclass
class AssembledContext:
    sources: List[ContextSource] = field(default_factory=list)
    total_tokens: int = 0
    dropped: List[str] = field(default_factory=list)   # names of sources dropped entirely
    truncated: List[str] = field(default_factory=list)  # names of sources partially cut

    def as_messages(self) -> List[dict]:
        """Return in position order as role/content dicts, ready for an LLM call."""
        ordered = sorted(self.sources, key=lambda s: s.position)
        return [{"role": s.role, "content": s.content} for s in ordered]

    def as_string(self, separator: str = "\n\n") -> str:
        ordered = sorted(self.sources, key=lambda s: s.position)
        return separator.join(s.content for s in ordered)


class ContextAssembler:
    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self._sources: List[ContextSource] = []
        self._next_position = 0

    def add(self, source: ContextSource) -> "ContextAssembler":
        if source.position == 0 and self._sources:
            source.position = self._next_position
        self._next_position += 1
        self._sources.append(source)
        return self

    def add_text(
        self,
        name: str,
        content: str,
        priority: int = 5,
        pinned: bool = False,
        role: str = "system",
        truncate_from: TruncateFrom = "start",
    ) -> "ContextAssembler":
        self.add(ContextSource(
            name=name, content=content, priority=priority,
            pinned=pinned, role=role, truncate_from=truncate_from,
        ))
        return self

    def add_history(
        self,
        turns: List[dict],
        base_priority: int = 4,
        recency_boost: bool = True,
    ) -> "ContextAssembler":
        """
        turns: list of {"role": "user"|"assistant", "content": str}, oldest first.
        Recent turns get a higher priority so they survive trimming before
        older ones do.
        """
        n = len(turns)
        for i, turn in enumerate(turns):
            priority = base_priority + (i if recency_boost else 0)
            self.add(ContextSource(
                name=f"history_{i}",
                content=turn["content"],
                priority=priority,
                pinned=False,
                role=turn.get("role", "user"),
                truncate_from="start",
            ))
        return self

    def assemble(self) -> AssembledContext:
        pinned = [s for s in self._sources if s.pinned]
        rest = [s for s in self._sources if not s.pinned]

        pinned_tokens = sum(s.tokens() for s in pinned)
        if pinned_tokens > self.max_tokens:
            raise ValueError(
                f"Pinned sources alone ({pinned_tokens} tokens) exceed max_tokens "
                f"({self.max_tokens}). Increase max_tokens or unpin something."
            )

        budget = self.max_tokens - pinned_tokens
        rest_sorted = sorted(rest, key=lambda s: s.priority, reverse=True)

        included: List[ContextSource] = list(pinned)
        dropped: List[str] = []
        truncated: List[str] = []

        for source in rest_sorted:
            cost = source.tokens()
            if cost <= budget:
                included.append(source)
                budget -= cost
                continue

            if budget <= 0:
                dropped.append(source.name)
                continue

            # Partially fits: truncate to remaining budget.
            max_chars = budget * TOKEN_CHARS_PER_TOKEN
            if source.truncate_from == "end":
                new_content = source.content[:max_chars]
            else:
                new_content = source.content[-max_chars:]

            if not new_content.strip():
                dropped.append(source.name)
                continue

            truncated_source = ContextSource(
                name=source.name, content=new_content, priority=source.priority,
                pinned=False, position=source.position, role=source.role,
                truncate_from=source.truncate_from,
            )
            included.append(truncated_source)
            truncated.append(source.name)
            budget = 0

        total_tokens = sum(s.tokens() for s in included)
        return AssembledContext(
            sources=included, total_tokens=total_tokens,
            dropped=dropped, truncated=truncated,
        )
