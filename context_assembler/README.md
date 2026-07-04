# synon_context_assembler

Deterministic algorithm for assembling an LLM context window. Not an LLM
call — it decides what goes into the prompt before `llm_caller.py` (or
whatever sends the request) ever fires.

Built for the "bolt an AI assistant onto a SaaS app" pattern: system
prompt + user facts + conversation history + optional RAG snippets,
trimmed to fit a token budget without blowing it.

## How trimming works

- **Pinned** sources (system prompt, current user message) are always
  included, never trimmed. If pinned sources alone exceed `max_tokens`,
  it raises — that's a config problem, not something to silently truncate.
- **Non-pinned** sources are selected highest-priority-first. Once the
  budget runs out, a source that partially fits gets truncated; anything
  left over is dropped entirely.
- Final output is reordered back to natural reading order (system → facts
  → history → current message), regardless of priority order.

## Quick start

```python
from context_assembler import ContextAssembler
from backends import InMemoryBackend

backend = InMemoryBackend()
backend.set_fact("user_123", "plan", "Pro")
backend.append_history("session_abc", "user", "How do I export a report?")
backend.append_history("session_abc", "assistant", "Go to Reports > Export.")

assembler = ContextAssembler(max_tokens=4000)
assembler.add_text("system", "You are a helpful SaaS support assistant.", pinned=True, role="system")

facts = backend.get_facts("user_123")
assembler.add_text("user_facts", f"User facts: {facts}", priority=6)

history = backend.get_history("session_abc", limit=10)
assembler.add_history(history, base_priority=4)

assembler.add_text("current_message", "Can I export to CSV too?", pinned=True, role="user")

result = assembler.assemble()
messages = result.as_messages()   # -> feed straight into llm_caller.py
print(result.total_tokens, result.dropped, result.truncated)
```

## Backends

- `InMemoryBackend` — zero setup, data lives for the process lifetime. Good
  for local dev/tests.
- `SupabaseBackend` — persists facts + history via `context_facts` /
  `context_history` tables (see `schema.sql`). Requires `SUPABASE_URL` +
  `SUPABASE_KEY` (service role) in `.env`, and the `supabase` package.

Swap backends without touching `ContextAssembler` — it only deals with
`ContextSource` objects, it doesn't know or care where they came from.

## Token estimation

Default is a crude `len(text) // 4` heuristic (no dependencies). If you
need precision, replace `estimate_tokens()` in `context_assembler.py` with
a real tokenizer — the trimming algorithm doesn't care how tokens are
counted, only that the estimate is consistent.
