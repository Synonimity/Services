import pytest
from httpx import AsyncClient
from itsdangerous import URLSafeTimedSerializer
from app.routers.oauth import _STATE_MAX_AGE_SECONDS

pytestmark = pytest.mark.asyncio

async def test_oauth_authorize_returns_url_and_cookie(client: AsyncClient):
    response = await client.get("/oauth/apple/authorize")
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "apple.com" in data["authorization_url"]
    
    # Check that pkce_verifier cookie was set
    cookies = response.cookies
    assert "pkce_verifier" in cookies

async def test_oauth_callback_invalid_state(client: AsyncClient):
    # State cannot be parsed
    response = await client.get(
        "/oauth/apple/callback",
        params={"code": "dummycode", "state": "invalidstate"}
    )
    assert response.status_code == 400
    assert "Invalid OAuth state" in response.json()["detail"]

async def test_oauth_callback_missing_cookie(client: AsyncClient):
    from app.config import get_settings
    settings = get_settings()
    serializer = URLSafeTimedSerializer(settings.secret_key, salt="oauth-state")
    valid_state = serializer.dumps({"provider": "apple", "nonce": "dummy"})

    # Send valid state but missing the pkce_verifier cookie
    response = await client.get(
        "/oauth/apple/callback",
        params={"code": "dummycode", "state": valid_state}
    )
    assert response.status_code == 400
    assert "Missing PKCE verifier cookie" in response.json()["detail"]
