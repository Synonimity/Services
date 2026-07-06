from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitConfig(BaseSettings):
    """
    Configuration for Rate Limiting.
    """
    backend: Literal["memory", "redis"] = Field("memory", description="Backend to use")
    redis_url: Optional[str] = Field(None, description="Redis URL if using redis backend")
    
    default_capacity: int = Field(10, description="Default token bucket capacity")
    default_window_seconds: int = Field(60, description="Default refill window")
    key_prefix: str = Field("synon_rl", description="Prefix for all keys in backend")

    model_config = SettingsConfigDict(env_prefix="RATELIMIT_", extra="ignore")
