from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ContextAssemblerConfig(BaseSettings):
    """
    Configuration for Context Assembler.
    """
    max_tokens: int = Field(4000, description="Default max tokens for the context")
    supabase_url: Optional[str] = Field(None, description="Supabase URL for the backend")
    supabase_key: Optional[str] = Field(None, description="Supabase Key for the backend")
    context_facts_table: str = Field("context_facts", description="Table name for facts")
    context_history_table: str = Field("context_history", description="Table name for history")

    model_config = SettingsConfigDict(env_prefix="CONTEXT_", extra="ignore")
