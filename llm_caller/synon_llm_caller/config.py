from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMCallerConfig(BaseSettings):
    """
    Configuration for the LLM Caller.
    Defaults to Anthropic-style settings.
    """
    api_key: str = Field(..., description="API key for the LLM provider")
    api_url: str = Field("https://api.anthropic.com/v1/messages", description="Endpoint URL")
    model: str = Field("claude-3-5-sonnet-20240620", description="Model identifier")
    max_tokens: int = Field(1000, description="Max tokens for the response")
    timeout_seconds: int = Field(60, description="Request timeout")
    anthropic_version: str = Field("2023-06-01", description="Anthropic-specific version header")

    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")
