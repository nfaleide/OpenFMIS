"""Reference data endpoint tests -- crop types, FCIC codes, tillage, units."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.user import User
from openfmis.security.password import hash_password


@pytest.fixture
async def ref_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="refuser",
        email="ref@test.com",
        password_hash=hash_password("refpass123"),
        full_name="Ref User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _login(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_crop_types(client: AsyncClient, ref_user: User):
    token = await _login(client, "refuser", "refpass123")
    resp = await client.get(
        "/api/v1/reference/crop-types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    codes = {item["code"] for item in data}
    assert 1 in codes  # Corn
    assert 5 in codes  # Soybeans
    # Check structure
    corn = next(item for item in data if item["code"] == 1)
    assert corn["name"] == "Corn"


@pytest.mark.asyncio
async def test_fcic_crops(client: AsyncClient, ref_user: User):
    token = await _login(client, "refuser", "refpass123")
    resp = await client.get(
        "/api/v1/reference/fcic-crops",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    codes = {item["code"] for item in data}
    assert 41 in codes  # Corn (FCIC)
    assert 81 in codes  # Soybeans (FCIC)


@pytest.mark.asyncio
async def test_tillage_types(client: AsyncClient, ref_user: User):
    token = await _login(client, "refuser", "refpass123")
    resp = await client.get(
        "/api/v1/reference/tillage-types",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "no_till" in data
    assert "moldboard" in data


@pytest.mark.asyncio
async def test_units(client: AsyncClient, ref_user: User):
    token = await _login(client, "refuser", "refpass123")
    resp = await client.get(
        "/api/v1/reference/units",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "bu/ac" in data
    assert "lb/ac" in data


@pytest.mark.asyncio
async def test_reference_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/reference/crop-types")
    assert resp.status_code in (401, 403)
