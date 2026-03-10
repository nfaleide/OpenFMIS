"""UserService + User API endpoint tests."""

import pytest
from httpx import AsyncClient


async def _login(
    client: AsyncClient, username: str = "testuser", password: str = "testpassword123"
) -> str:
    """Helper: login and return access token."""
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_users(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.get("/api/v1/users", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(u["username"] == "testuser" for u in data["items"])


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.get(f"/api/v1/users/{test_user.id}", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000000", headers=_auth(token)
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "securepass123",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_user_duplicate_username(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "testuser", "password": "somepassword123"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_user(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.patch(
        f"/api/v1/users/{test_user.id}",
        headers=_auth(token),
        json={"full_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        f"/api/v1/users/{test_user.id}/change-password",
        headers=_auth(token),
        json={"current_password": "testpassword123", "new_password": "newpassword456"},
    )
    assert resp.status_code == 204

    # Verify new password works
    login_resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "newpassword456"},
    )
    assert login_resp.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        f"/api/v1/users/{test_user.id}/change-password",
        headers=_auth(token),
        json={"current_password": "wrongpassword", "new_password": "newpassword456"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_user(client: AsyncClient, test_user):
    token = await _login(client)

    # Create a user to delete
    create_resp = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "todelete", "password": "deletepass123"},
    )
    user_id = create_resp.json()["id"]

    # Delete
    resp = await client.delete(f"/api/v1/users/{user_id}", headers=_auth(token))
    assert resp.status_code == 204

    # Verify gone
    get_resp = await client.get(f"/api/v1/users/{user_id}", headers=_auth(token))
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_list_users_filter_active(client: AsyncClient, test_user, inactive_user):
    token = await _login(client)
    resp = await client.get("/api/v1/users?is_active=true", headers=_auth(token))
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()["items"]]
    assert "testuser" in usernames
    assert "inactiveuser" not in usernames
