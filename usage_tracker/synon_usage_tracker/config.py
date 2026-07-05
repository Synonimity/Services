from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UsageTrackerConfig(BaseSettings):
    """
    Configuration for Usage Tracker.
    """
    supabase_url: Optional[str] = Field(None, description="Supabase URL for the backend")
    supabase_key: Optional[str] = Field(None, description="Supabase Key for the backend")
    usage_events_table: str = Field("usage_events", description="Table name for usage events")
    default_plan: str = Field("trial", description="Default plan for quota checks")

    model_config = SettingsConfigDict(env_prefix="USAGE_", extra="ignore")
