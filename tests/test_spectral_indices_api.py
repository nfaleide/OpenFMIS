"""Tests for spectral indices API endpoints."""

import pytest

from openfmis.models.spectral_index import SpectralIndexDefinition
from openfmis.services.band_math import BUILTIN_INDICES, extract_required_bands


@pytest.fixture
async def seed_builtins(db_session):
    """Seed a few builtin indices for API tests."""
    for idx in BUILTIN_INDICES[:5]:
        record = SpectralIndexDefinition(
            slug=idx["slug"],
            display_name=idx["display_name"],
            formula=idx["formula"],
            required_bands=extract_required_bands(idx["formula"]),
            category=idx.get("category", "vegetation"),
            is_builtin=True,
        )
        db_session.add(record)
    await db_session.flush()


class TestSpectralIndicesAPI:
    async def test_list_indices(self, client, test_user, seed_builtins):
        # Login
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/satshot/indices/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 5

    async def test_get_index(self, client, test_user, seed_builtins):
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/satshot/indices/ndvi", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["slug"] == "ndvi"

    async def test_create_custom_index(self, client, test_user, seed_builtins):
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/satshot/indices/",
            headers=headers,
            json={
                "slug": "custom_test",
                "display_name": "Custom Test",
                "formula": "(nir - red) * 2",
                "category": "custom",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["slug"] == "custom_test"
        assert resp.json()["is_builtin"] is False

    async def test_validate_formula(self, client, test_user):
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/satshot/indices/validate",
            headers=headers,
            json={
                "formula": "(nir - red) / (nir + red)",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert sorted(data["required_bands"]) == ["nir", "red"]

    async def test_validate_bad_formula(self, client, test_user):
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/satshot/indices/validate",
            headers=headers,
            json={
                "formula": "eval(nir)",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    async def test_cannot_delete_builtin(self, client, test_user, seed_builtins):
        login = await client.post(
            "/api/v1/login",
            json={
                "username": "testuser",
                "password": "testpassword123",
            },
        )
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.delete("/api/v1/satshot/indices/ndvi", headers=headers)
        assert resp.status_code == 403
