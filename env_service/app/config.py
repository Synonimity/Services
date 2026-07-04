from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str

    environment: str = "development"
    base_url: str = "http://localhost:8000"
    allowed_origins: str = ""
    allowed_client_ips: str = ""

    master_encryption_key: str
    service_admin_key: str

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_client_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.allowed_client_ips.split(",") if ip.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
