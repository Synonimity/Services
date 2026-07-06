from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LicensingConfig(BaseSettings):
    """
    Configuration for the Licensing service.
    """
    supabase_url: str = Field(..., description="Supabase URL")
    supabase_service_role_key: str = Field(..., description="Supabase Service Role Key")

    license_key_segment_length: int = Field(4, description="Length of each key segment")
    license_key_segment_count: int = Field(4, description="Number of segments in a key")

    license_keys_table: str = Field("license_keys", description="Table for issued licenses")
    license_key_pool_table: str = Field("license_key_pool", description="Table for pre-generated keys")
    trial_usage_table: str = Field("trial_usage", description="Table for tracking trial usage")

    model_config = SettingsConfigDict(env_prefix="LICENSING_", extra="ignore")
