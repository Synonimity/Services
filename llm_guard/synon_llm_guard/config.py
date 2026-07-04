from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMGuardConfig(BaseSettings):
    """
    Configuration for LLM Guard security layer.
    """
    injection_flag_threshold: float = Field(0.3, description="Score at which to flag input")
    injection_block_threshold: float = Field(0.7, description="Score at which to block input")
    pii_mode: str = Field("redact", description="Mode for PII scrubber: 'redact' or 'flag_only'")

    model_config = SettingsConfigDict(env_prefix="LLM_GUARD_", extra="ignore")
