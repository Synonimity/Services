from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerConfig(BaseSettings):
    """
    Configuration for the Scheduler.
    """
    supabase_url: str = Field(..., description="Supabase URL")
    supabase_service_role_key: str = Field(..., description="Supabase Service Role Key")
    
    jobs_table: str = Field("scheduled_jobs", description="Table for one-off jobs")
    recurring_jobs_table: str = Field("recurring_jobs", description="Table for recurring jobs")
    
    job_base_backoff_seconds: int = Field(30, description="Base backoff for retries")
    job_max_backoff_seconds: int = Field(3600, description="Max backoff for retries")
    job_claim_timeout_minutes: int = Field(10, description="Minutes before a 'running' job is stale")

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_", extra="ignore")
