"""Logo tests — per-group branding upsert."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.schemas.logo import LogoUpsert
from openfmis.services.logo import LogoService


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "testuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="LogoCo")
    db_session.add(group)
    await db_session.flush()
    return group


# ── Unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_logo(db_session: AsyncSession, test_group):
    svc = LogoService(db_session)
    logo = await svc.upsert(
        LogoUpsert(
            group_id=test_group.id,
            storage_url="gs://bucket/logos/farmco.png",
            file_type="png",
            width=200,
            height=100,
        )
    )
    assert logo.storage_url == "gs://bucket/logos/farmco.png"
    assert logo.width == 200


@pytest.mark.asyncio
async def test_upsert_updates_existing(db_session: AsyncSession, test_group):
    svc = LogoService(db_session)
    await svc.upsert(LogoUpsert(group_id=test_group.id, storage_url="gs://bucket/old.png"))
    updated = await svc.upsert(
        LogoUpsert(group_id=test_group.id, storage_url="gs://bucket/new.png")
    )
    assert updated.storage_url == "gs://bucket/new.png"

    # Should still be just one logo
    logo = await svc.get_by_group(test_group.id)
    assert logo.storage_url == "gs://bucket/new.png"


@pytest.mark.asyncio
async def test_delete_logo(db_session: AsyncSession, test_group):
    svc = LogoService(db_session)
    await svc.upsert(LogoUpsert(group_id=test_group.id, storage_url="gs://bucket/del.png"))
    await svc.delete(test_group.id)
    with pytest.raises(Exception):
        await svc.get_by_group(test_group.id)


# ── API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_upsert_logo(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.put(
        "/api/v1/logos",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "storage_url": "gs://bucket/api.png",
            "file_type": "png",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["storage_url"] == "gs://bucket/api.png"


@pytest.mark.asyncio
async def test_api_get_logo(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    await client.put(
        "/api/v1/logos",
        headers=_auth(token),
        json={"group_id": str(test_group.id), "storage_url": "gs://bucket/get.png"},
    )
    resp = await client.get(f"/api/v1/logos/{test_group.id}", headers=_auth(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_delete_logo(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    await client.put(
        "/api/v1/logos",
        headers=_auth(token),
        json={"group_id": str(test_group.id), "storage_url": "gs://bucket/del.png"},
    )
    resp = await client.delete(f"/api/v1/logos/{test_group.id}", headers=_auth(token))
    assert resp.status_code == 204
