"""
Centralized configuration. Everything sensitive comes from environment
variables / .env - nothing secret is ever hardcoded.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str

    # JWT
    jwt_private_key_path: str = "./keys/private.pem"
    jwt_public_key_path: str = "./keys/public.pem"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    jwt_issuer: str = "kerfsuite-auth"
    jwt_audience: str = "kerfsuite"

    # App
    environment: str = "development"
    allowed_origins: str = "http://localhost:3000"
    base_url: str = "http://localhost:8000"
    cookie_domain: str | None = None
    secret_key: str

    # Account lockout / brute force protection
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # OAuth - Google
    google_client_id: str = ""
    google_client_secret: str = ""

    # OAuth - Facebook
    facebook_client_id: str = ""
    facebook_client_secret: str = ""

    # OAuth - Discord
    discord_client_id: str = ""
    discord_client_secret: str = ""

    # OAuth - Apple
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key_path: str = "./keys/apple_auth_key.p8"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def jwt_private_key(self) -> str:
        return Path(self.jwt_private_key_path).read_text()

    @property
    def jwt_public_key(self) -> str:
        return Path(self.jwt_public_key_path).read_text()


@lru_cache
def get_settings() -> Settings:
    return Settings()
