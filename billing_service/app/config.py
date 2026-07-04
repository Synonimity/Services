from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    environment: str = "development"
    base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:3000"
    service_api_key: str

    payfast_return_url: str
    payfast_cancel_url: str

    payfast_mode: str = "sandbox"  # "sandbox" or "live"
    payfast_merchant_id: str
    payfast_merchant_key: str
    payfast_passphrase: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def payfast_base_url(self) -> str:
        if self.payfast_mode == "live":
            return "https://www.payfast.co.za"
        return "https://sandbox.payfast.co.za"

    @property
    def payfast_api_base_url(self) -> str:
        # Subscription-management API host is the same regardless of
        # sandbox/live - sandbox-ness is determined by which merchant_id
        # you authenticate with.
        return "https://api.payfast.co.za"


@lru_cache
def get_settings() -> Settings:
    return Settings()
