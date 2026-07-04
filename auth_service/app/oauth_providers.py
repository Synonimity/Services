"""
Provider configuration for manual OAuth2 authorization-code flows.
Going manual (rather than a framework client) keeps the CSRF `state`
handling explicit, avoids relying on server-side sessions (so this service
scales horizontally without sticky sessions), and makes the token exchange
for every provider auditable in one place (see app/routers/oauth.py).
"""
import time
from dataclasses import dataclass
from pathlib import Path

import jwt

from app.config import get_settings

settings = get_settings()


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    authorize_url: str
    token_url: str
    userinfo_url: str | None
    client_id: str
    client_secret: str
    scope: str


PROVIDERS: dict[str, ProviderConfig] = {
    "google": ProviderConfig(
        name="google",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scope="openid email profile",
    ),
    "facebook": ProviderConfig(
        name="facebook",
        authorize_url="https://www.facebook.com/v19.0/dialog/oauth",
        token_url="https://graph.facebook.com/v19.0/oauth/access_token",
        userinfo_url="https://graph.facebook.com/me?fields=id,name,email",
        client_id=settings.facebook_client_id,
        client_secret=settings.facebook_client_secret,
        scope="email public_profile",
    ),
    "discord": ProviderConfig(
        name="discord",
        authorize_url="https://discord.com/api/oauth2/authorize",
        token_url="https://discord.com/api/oauth2/token",
        userinfo_url="https://discord.com/api/users/@me",
        client_id=settings.discord_client_id,
        client_secret=settings.discord_client_secret,
        scope="identify email",
    ),
    "apple": ProviderConfig(
        name="apple",
        authorize_url="https://appleid.apple.com/auth/authorize",
        token_url="https://appleid.apple.com/auth/token",
        userinfo_url=None,  # Apple puts identity in the token's id_token claims instead
        client_id=settings.apple_client_id,
        client_secret="",  # generated dynamically, see below
        scope="name email",
    ),
}


def generate_apple_client_secret() -> str:
    """
    Apple requires the 'client_secret' sent during token exchange to be a
    JWT, signed with ES256 using your Sign-in-with-Apple private key (.p8),
    asserting your team/key/client identifiers. Minted fresh per request and
    used immediately, so a short 5-minute lifetime is fine.
    """
    private_key = Path(settings.apple_private_key_path).read_text()
    now = int(time.time())

    payload = {
        "iss": settings.apple_team_id,
        "iat": now,
        "exp": now + 300,
        "aud": "https://appleid.apple.com",
        "sub": settings.apple_client_id,
    }
    headers = {"kid": settings.apple_key_id, "alg": "ES256"}

    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
