"""
Pluggable backends for persisting usage events.

Default is in-memory (zero setup, good for tests). SupabaseBackend
persists events so usage/quota checks survive restarts and work across
multiple app instances - the expected setup once this is wired into a
real SaaS app alongside licensing/ratelimit.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional
import os


class UsageBackend(ABC):
    @abstractmethod
    def log_event(self, event: dict) -> None:
        """event: {user_id, session_id, model, input_tokens, output_tokens, cost, created_at}"""
        ...

    @abstractmethod
    def get_events(self, user_id: str, since: Optional[datetime] = None) -> List[dict]:
        ...


class InMemoryBackend(UsageBackend):
    def __init__(self):
        self._events: List[dict] = []

    def log_event(self, event: dict) -> None:
        self._events.append(event)

    def get_events(self, user_id: str, since: Optional[datetime] = None) -> List[dict]:
        events = [e for e in self._events if e["user_id"] == user_id]
        if since:
            events = [e for e in events if e["created_at"] >= since]
        return events


class SupabaseBackend(UsageBackend):
    """
    Requires the `supabase` package and SUPABASE_URL / SUPABASE_KEY env vars
    (service role key recommended for server-side writes). Expects the
    `usage_events` table defined in schema.sql.
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

    def log_event(self, event: dict) -> None:
        row = dict(event)
        row["created_at"] = row["created_at"].isoformat()
        self.client.table("usage_events").insert(row).execute()

    def get_events(self, user_id: str, since: Optional[datetime] = None) -> List[dict]:
        query = self.client.table("usage_events").select("*").eq("user_id", user_id)
        if since:
            query = query.gte("created_at", since.isoformat())
        res = query.execute()
        events = []
        for row in res.data:
            row["created_at"] = datetime.fromisoformat(row["created_at"])
            events.append(row)
        return events
