from typing import Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheConfig(BaseSettings):
    """
    Configuration for Caching.
    """
    backend: Literal["memory", "redis"] = Field("memory", description="Backend to use")
    default_ttl_seconds: int = Field(300, description="Default TTL")
    redis_url: Optional[str] = Field(None, description="Redis URL if using redis")
    key_prefix: str = Field("synon", description="Prefix for all keys")

    model_config = SettingsConfigDict(env_prefix="CACHE_", extra="ignore")
