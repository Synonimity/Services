from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebhooksConfig(BaseSettings):
    """
    Configuration for Webhooks.
    """
    supabase_url: str = Field(..., description="Supabase URL")
    supabase_service_role_key: str = Field(..., description="Supabase Service Role Key")

    max_retries: int = Field(5, description="Max retry attempts for failed handlers")
    base_backoff_seconds: int = Field(30, description="Base backoff for retries")
    max_backoff_seconds: int = Field(3600, description="Max backoff for retries")
    
    idempotency_window_hours: int = Field(72, description="Hours a successful event's key remains valid")
    
    events_table: str = Field("webhook_events", description="Table name for events")

    model_config = SettingsConfigDict(env_prefix="WEBHOOKS_", extra="ignore")
