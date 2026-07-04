"""
Pluggable backends for fetching the raw material that feeds into
ContextAssembler: per-user facts and per-session conversation history.

Default is pure in-memory (zero setup, good for tests / single-process
demos). SupabaseBackend persists facts + history so context survives
restarts and works across multiple app instances - the expected setup for
a SaaS app with an AI assistant bolted on.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import os


class ContextBackend(ABC):
    @abstractmethod
    def get_facts(self, user_id: str) -> Dict[str, str]:
        """Return key/value facts about a user (name, plan, preferences, etc.)."""
        ...

    @abstractmethod
    def set_fact(self, user_id: str, key: str, value: str) -> None:
        ...

    @abstractmethod
    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        """Return recent turns, oldest first: [{"role": ..., "content": ...}, ...]."""
        ...

    @abstractmethod
    def append_history(self, session_id: str, role: str, content: str) -> None:
        ...


class InMemoryBackend(ContextBackend):
    """Zero-setup backend. Data lives only for the life of the process."""

    def __init__(self):
        self._facts: Dict[str, Dict[str, str]] = {}
        self._history: Dict[str, List[Dict[str, str]]] = {}

    def get_facts(self, user_id: str) -> Dict[str, str]:
        return dict(self._facts.get(user_id, {}))

    def set_fact(self, user_id: str, key: str, value: str) -> None:
        self._facts.setdefault(user_id, {})[key] = value

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        return self._history.get(session_id, [])[-limit:]

    def append_history(self, session_id: str, role: str, content: str) -> None:
        self._history.setdefault(session_id, []).append({"role": role, "content": content})


class SupabaseBackend(ContextBackend):
    """
    Requires the `supabase` package and SUPABASE_URL / SUPABASE_KEY env vars
    (service role key recommended for server-side writes - see .env_example).
    Expects the tables defined in schema.sql.
    """

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        try:
            from supabase import create_client
        except ImportError as e:
            raise ImportError(
                "SupabaseBackend requires the 'supabase' package: pip install supabase"
            ) from e

        url = url or os.getenv("SUPABASE_URL")
        key = key or os.getenv("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set to use SupabaseBackend.")

        self.client = create_client(url, key)

    def get_facts(self, user_id: str) -> Dict[str, str]:
        res = self.client.table("context_facts").select("key,value").eq("user_id", user_id).execute()
        return {row["key"]: row["value"] for row in res.data}

    def set_fact(self, user_id: str, key: str, value: str) -> None:
        self.client.table("context_facts").upsert({
            "user_id": user_id, "key": key, "value": value,
        }, on_conflict="user_id,key").execute()

    def get_history(self, session_id: str, limit: int = 20) -> List[Dict[str, str]]:
        res = (
            self.client.table("context_history")
            .select("role,content,created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed([{"role": r["role"], "content": r["content"]} for r in res.data]))

    def append_history(self, session_id: str, role: str, content: str) -> None:
        self.client.table("context_history").insert({
            "session_id": session_id, "role": role, "content": content,
        }).execute()
