"""Preference tests — upsert + per-user namespaced settings."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.schemas.preference import PreferenceUpsert
from openfmis.services.preference import PreferenceService


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "testuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_preference(db_session: AsyncSession, test_user):
    svc = PreferenceService(db_session)
    pref = await svc.upsert(
        test_user.id,
        PreferenceUpsert(namespace="web", data={"theme": "dark", "zoom": 12}),
    )
    assert pref.namespace == "web"
    assert pref.data["theme"] == "dark"


@pytest.mark.asyncio
async def test_upsert_updates_existing(db_session: AsyncSession, test_user):
    svc = PreferenceService(db_session)
    await svc.upsert(test_user.id, PreferenceUpsert(namespace="web", data={"theme": "dark"}))
    updated = await svc.upsert(
        test_user.id, PreferenceUpsert(namespace="web", data={"theme": "light"})
    )
    assert updated.data["theme"] == "light"


@pytest.mark.asyncio
async def test_list_preferences(db_session: AsyncSession, test_user):
    svc = PreferenceService(db_session)
    await svc.upsert(test_user.id, PreferenceUpsert(namespace="mobile", data={"version": 2}))
    await svc.upsert(test_user.id, PreferenceUpsert(namespace="web", data={"theme": "dark"}))
    prefs = await svc.list_for_user(test_user.id)
    assert len(prefs) >= 2


@pytest.mark.asyncio
async def test_delete_preference(db_session: AsyncSession, test_user):
    svc = PreferenceService(db_session)
    await svc.upsert(test_user.id, PreferenceUpsert(namespace="temp", data={"key": "val"}))
    await svc.delete(test_user.id, "temp")
    with pytest.raises(Exception):
        await svc.get(test_user.id, "temp")


# ── API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_upsert_preference(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.put(
        "/api/v1/preferences",
        headers=_auth(token),
        json={"namespace": "web", "data": {"theme": "dark"}},
    )
    assert resp.status_code == 200
    assert resp.json()["namespace"] == "web"


@pytest.mark.asyncio
async def test_api_get_preference(client: AsyncClient, test_user):
    token = await _login(client)
    await client.put(
        "/api/v1/preferences",
        headers=_auth(token),
        json={"namespace": "api_test", "data": {"key": "val"}},
    )
    resp = await client.get("/api/v1/preferences/api_test", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["data"]["key"] == "val"


@pytest.mark.asyncio
async def test_api_list_preferences(client: AsyncClient, test_user):
    token = await _login(client)
    await client.put(
        "/api/v1/preferences", headers=_auth(token), json={"namespace": "ns1", "data": {}}
    )
    resp = await client.get("/api/v1/preferences", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1


@pytest.mark.asyncio
async def test_api_delete_preference(client: AsyncClient, test_user):
    token = await _login(client)
    await client.put(
        "/api/v1/preferences", headers=_auth(token), json={"namespace": "to_delete", "data": {}}
    )
    resp = await client.delete("/api/v1/preferences/to_delete", headers=_auth(token))
    assert resp.status_code == 204
