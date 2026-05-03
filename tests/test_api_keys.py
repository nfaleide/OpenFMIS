"""Tests for API key CRUD, logout enforcement, and revoked key rejection."""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestLogoutEnforcement:
    """Verify that get_current_user checks the token blacklist."""

    async def test_logout_revokes_token(self, client: AsyncClient, test_user):
        """After logout, the same access token should be rejected."""
        # Login
        login_resp = await client.post(
            "/api/v1/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Confirm token works
        me_resp = await client.get("/api/v1/me", headers=headers)
        assert me_resp.status_code == 200

        # Logout
        logout_resp = await client.post("/api/v1/logout", headers=headers)
        assert logout_resp.status_code == 204

        # Token should now be rejected
        me_resp2 = await client.get("/api/v1/me", headers=headers)
        assert me_resp2.status_code == 401

    async def test_logout_does_not_affect_other_tokens(self, client: AsyncClient, test_user):
        """Logging out one token should not invalidate another."""
        # Login twice
        resp1 = await client.post(
            "/api/v1/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        resp2 = await client.post(
            "/api/v1/login",
            json={"username": "testuser", "password": "testpassword123"},
        )
        token1 = resp1.json()["access_token"]
        token2 = resp2.json()["access_token"]

        # Logout token1
        await client.post("/api/v1/logout", headers={"Authorization": f"Bearer {token1}"})

        # Token2 should still work
        me_resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token2}"})
        assert me_resp.status_code == 200


class TestAPIKeyEndpoints:
    """API key CRUD round-trip tests."""

    async def test_create_api_key(self, client: AsyncClient, auth_headers):
        resp = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "CI bot key"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "CI bot key"
        assert len(data["raw_key"]) == 64  # 32 bytes hex
        assert data["key_prefix"] == data["raw_key"][:8]
        assert "id" in data

    async def test_list_api_keys(self, client: AsyncClient, auth_headers):
        # Create two keys
        await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Key A"},
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Key B"},
            headers=auth_headers,
        )

        resp = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 2
        names = {k["name"] for k in keys}
        assert "Key A" in names
        assert "Key B" in names

    async def test_revoke_api_key(self, client: AsyncClient, auth_headers):
        # Create
        create_resp = await client.post(
            "/api/v1/auth/api-keys",
            json={"name": "Temp key"},
            headers=auth_headers,
        )
        key_id = create_resp.json()["id"]

        # Revoke
        revoke_resp = await client.delete(
            f"/api/v1/auth/api-keys/{key_id}",
            headers=auth_headers,
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["revoked_at"] is not None

        # Should not appear in default list
        list_resp = await client.get("/api/v1/auth/api-keys", headers=auth_headers)
        ids = [k["id"] for k in list_resp.json()]
        assert key_id not in ids

        # But appears with include_revoked
        list_resp2 = await client.get(
            "/api/v1/auth/api-keys?include_revoked=true",
            headers=auth_headers,
        )
        ids2 = [k["id"] for k in list_resp2.json()]
        assert key_id in ids2

    async def test_revoke_nonexistent_key(self, client: AsyncClient, auth_headers):
        resp = await client.delete(
            f"/api/v1/auth/api-keys/{uuid.uuid4()}",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestAPIKeyService:
    """Service-level tests for API key verification."""

    async def test_verify_valid_key(self, db_session, test_user):
        from openfmis.services.api_key import APIKeyService

        svc = APIKeyService(db_session)
        key, raw = await svc.create_key(test_user.id, "test key")

        verified = await svc.verify_key(raw)
        assert verified.id == key.id
        assert verified.last_used_at is not None

    async def test_verify_revoked_key(self, db_session, test_user):
        from openfmis.exceptions import AuthenticationError
        from openfmis.services.api_key import APIKeyService

        svc = APIKeyService(db_session)
        key, raw = await svc.create_key(test_user.id, "will revoke")
        await svc.revoke_key(key.id, test_user.id)

        with pytest.raises(AuthenticationError, match="revoked"):
            await svc.verify_key(raw)

    async def test_verify_expired_key(self, db_session, test_user):
        from datetime import UTC, datetime, timedelta

        from openfmis.exceptions import AuthenticationError
        from openfmis.services.api_key import APIKeyService

        svc = APIKeyService(db_session)
        expired = datetime.now(UTC) - timedelta(hours=1)
        key, raw = await svc.create_key(test_user.id, "expired key", expires_at=expired)

        with pytest.raises(AuthenticationError, match="expired"):
            await svc.verify_key(raw)

    async def test_verify_invalid_key(self, db_session):
        from openfmis.exceptions import AuthenticationError
        from openfmis.services.api_key import APIKeyService

        svc = APIKeyService(db_session)
        with pytest.raises(AuthenticationError, match="Invalid"):
            await svc.verify_key("not-a-real-key")
