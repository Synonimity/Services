import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_login_success(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    response = await client.post(
        "/auth/login",
        json={
            "identifier": "testuser",
            "password": "P@ssw0rd123!"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

async def test_login_wrong_password(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    response = await client.post(
        "/auth/login",
        json={
            "identifier": "testuser",
            "password": "WrongPassword123!"
        }
    )
    assert response.status_code == 401

async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={
            "identifier": "nonexistent",
            "password": "WrongPassword123!"
        }
    )
    assert response.status_code == 401

async def test_login_account_lockout(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com", "P@ssw0rd123!")
    
    # max_failed_logins is 5 by default
    for _ in range(5):
        response = await client.post(
            "/auth/login",
            json={
                "identifier": "testuser",
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code == 401

    # 6th attempt should return 423 Locked
    response = await client.post(
        "/auth/login",
        json={
            "identifier": "testuser",
            "password": "WrongPassword123!"
        }
    )
    assert response.status_code == 423
