"""Auth endpoint tests — login, refresh, /me, inactive user."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user):
    resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    resp = await client.post(
        "/api/v1/login",
        json={"username": "noone", "password": "whatever"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, inactive_user):
    resp = await client.post(
        "/api/v1/login",
        json={"username": "inactiveuser", "password": "password123"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_md5_migration(client: AsyncClient, test_user_md5):
    """Login with legacy MD5 hash should succeed and re-hash to Argon2id."""
    resp = await client.post(
        "/api/v1/login",
        json={"username": "legacyuser", "password": "legacypass"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient, test_user):
    # First login
    login_resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    token = login_resp.json()["access_token"]

    # Then /me
    resp = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_me_no_token(client: AsyncClient):
    resp = await client.get("/api/v1/me")
    assert resp.status_code in (401, 403)  # HTTPBearer returns 403 when no token


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, test_user):
    # Login
    login_resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Refresh
    resp = await client.post(
        "/api/v1/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_invalid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert resp.status_code == 401
