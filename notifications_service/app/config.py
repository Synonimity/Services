from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    environment: str = "development"
    base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:3000"
    service_api_key: str

    resend_api_key: str
    resend_webhook_secret: str = ""

    email_from_address: str
    email_from_name: str = ""

    brand_name: str = "Your App"
    brand_color: str = "#FF6A00"
    brand_logo_url: str = ""
    brand_footer_text: str = ""

    slack_webhook_url: str = ""
    discord_webhook_url: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def from_header(self) -> str:
        return f"{self.email_from_name} <{self.email_from_address}>" if self.email_from_name else self.email_from_address


@lru_cache
def get_settings() -> Settings:
    return Settings()
