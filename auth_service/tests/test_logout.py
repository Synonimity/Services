import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_logout_success(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    response = await client.post(
        "/auth/login",
        json={"identifier": "testuser", "password": "P@ssw0rd123!"}
    )
    tokens = response.json()
    refresh_token = tokens["refresh_token"]

    # Logout
    response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 204

    # Try to refresh with the logged out token
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401
