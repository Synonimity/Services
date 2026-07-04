import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_refresh_success(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    # Login to get tokens
    response = await client.post(
        "/auth/login",
        json={"identifier": "testuser", "password": "P@ssw0rd123!"}
    )
    tokens = response.json()
    refresh_token = tokens["refresh_token"]

    # Refresh
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["refresh_token"] != refresh_token

async def test_refresh_revoked_replay(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    response = await client.post(
        "/auth/login",
        json={"identifier": "testuser", "password": "P@ssw0rd123!"}
    )
    tokens = response.json()
    refresh_token = tokens["refresh_token"]

    # Refresh once
    await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )

    # Refresh again with the same token (replay of revoked token)
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401
