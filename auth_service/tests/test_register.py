import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "StrongPassword123!"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password_hash" not in data

async def test_register_duplicate_username(client: AsyncClient, create_user):
    await create_user("testuser", "test@example.com")
    response = await client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "another@example.com",
            "password": "StrongPassword123!"
        }
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Username or email already registered."

async def test_register_duplicate_email(client: AsyncClient, create_user):
    await create_user("existinguser", "test@example.com")
    response = await client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "test@example.com",
            "password": "StrongPassword123!"
        }
    )
    assert response.status_code == 409

async def test_register_weak_password(client: AsyncClient):
    response = await client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "weak"
        }
    )
    assert response.status_code == 422
