from typing import List, Dict, Optional, Callable
from .models import ContextSource, AssemblyResult
from .config import ContextAssemblerConfig


class ContextAssemblerService:
    def __init__(
        self,
        config: ContextAssemblerConfig,
        tokenizer: Optional[Callable[[str], int]] = None
    ):
        self.config = config
        self.tokenizer = tokenizer or self._default_tokenizer
        self._sources: List[ContextSource] = []

    def _default_tokenizer(self, text: str) -> int:
        """Crude len // 4 heuristic if no real tokenizer provided."""
        return len(text) // 4

    def add_text(
        self,
        source_id: str,
        text: str,
        priority: int = 1,
        pinned: bool = False,
        role: str = "user"
    ) -> None:
        tokens = self.tokenizer(text)
        self._sources.append(ContextSource(
            id=source_id,
            text=text,
            priority=priority,
            pinned=pinned,
            role=role,
            estimated_tokens=tokens
        ))

    def add_history(self, history: List[Dict[str, str]], base_priority: int = 5) -> None:
        """Helper to add conversation history as separate sources."""
        for i, msg in enumerate(history):
            self.add_text(
                source_id=f"history_{i}",
                text=msg["content"],
                priority=base_priority,
                role=msg["role"]
            )

    def assemble(self, max_tokens: Optional[int] = None) -> AssemblyResult:
        limit = max_tokens or self.config.max_tokens
        
        # 1. Split into pinned and unpinned
        pinned = [s for s in self._sources if s.pinned]
        unpinned = sorted(
            [s for s in self._sources if not s.pinned],
            key=lambda x: x.priority,
            reverse=True
        )

        used = []
        dropped = []
        truncated = []
        current_tokens = sum(s.estimated_tokens for s in pinned)

        if current_tokens > limit:
            raise ValueError(f"Pinned content ({current_tokens}) exceeds token limit ({limit}).")

        used.extend(pinned)

        # 2. Add unpinned in priority order
        for source in unpinned:
            if current_tokens >= limit:
                dropped.append(source.id)
                continue

            if current_tokens + source.estimated_tokens <= limit:
                used.append(source)
                current_tokens += source.estimated_tokens
            else:
                # Truncate
                remaining = limit - current_tokens
                # Very crude truncation: take proportional chars
                chars_to_keep = int(len(source.text) * (remaining / source.estimated_tokens))
                source.text = source.text[:chars_to_keep] + "..."
                source.estimated_tokens = remaining
                used.append(source)
                truncated.append(source.id)
                current_tokens += remaining

        # 3. Restore natural order (by how they were added)
        # We find the original index in self._sources
        order_map = {s.id: i for i, s in enumerate(self._sources)}
        used.sort(key=lambda x: order_map[x.id])

        return AssemblyResult(
            text="\n".join(s.text for s in used),
            total_tokens=current_tokens,
            dropped=dropped,
            truncated=truncated,
            sources_used=used
        )

    def clear(self) -> None:
        self._sources = []
