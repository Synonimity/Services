from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    environment: str = "development"
    base_url: str = "http://localhost:8000"
    allowed_origins: str = "http://localhost:3000"
    service_api_key: str

    log_retention_days: int = 30

    notifications_base_url: str = ""
    notifications_api_key: str = ""
    notifications_alert_channel: str = "slack"
    alert_on_new_issues: bool = True
    alert_on_regressions: bool = True

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def alerting_enabled(self) -> bool:
        return bool(self.notifications_base_url and self.notifications_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
