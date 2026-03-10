"""Field tests — CRUD, geometry, versioning."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.schemas.field import FieldCreate
from openfmis.services.field import FieldService

# Sample GeoJSON — a simple square polygon in Kansas
SAMPLE_GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.0, 38.0],
                [-98.0, 38.01],
                [-97.99, 38.01],
                [-97.99, 38.0],
                [-98.0, 38.0],
            ]
        ]
    ],
}

SAMPLE_GEOJSON_V2 = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.0, 38.0],
                [-98.0, 38.02],
                [-97.98, 38.02],
                [-97.98, 38.0],
                [-98.0, 38.0],
            ]
        ]
    ],
}


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
    group = Group(id=uuid.uuid4(), name="FarmCo")
    db_session.add(group)
    await db_session.flush()
    return group


# ── Unit tests via FieldService ────────────────────────────────


@pytest.mark.asyncio
async def test_create_field_without_geometry(db_session: AsyncSession, test_group):
    svc = FieldService(db_session)
    field = await svc.create_field(FieldCreate(name="North 40", group_id=test_group.id))
    assert field.name == "North 40"
    assert field.version == 1
    assert field.is_current is True
    assert field.geometry is None


@pytest.mark.asyncio
async def test_create_field_with_geometry(db_session: AsyncSession, test_group):
    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(name="South Field", group_id=test_group.id, geometry_geojson=SAMPLE_GEOJSON)
    )
    assert field.name == "South Field"
    assert field.area_acres is not None
    assert field.area_acres > 0


@pytest.mark.asyncio
async def test_update_geometry_creates_version(db_session: AsyncSession, test_group):
    svc = FieldService(db_session)
    v1 = await svc.create_field(
        FieldCreate(name="Versioned Field", group_id=test_group.id, geometry_geojson=SAMPLE_GEOJSON)
    )
    assert v1.version == 1

    v2 = await svc.update_geometry(v1.id, SAMPLE_GEOJSON_V2)
    assert v2.version == 2
    assert v2.supersedes_id == v1.id
    assert v2.is_current is True

    # Reload v1 to check it's no longer current
    v1_reloaded = await svc.get_by_id(v1.id)
    assert v1_reloaded.is_current is False


@pytest.mark.asyncio
async def test_version_history(db_session: AsyncSession, test_group):
    svc = FieldService(db_session)
    v1 = await svc.create_field(
        FieldCreate(name="HistField", group_id=test_group.id, geometry_geojson=SAMPLE_GEOJSON)
    )
    v2 = await svc.update_geometry(v1.id, SAMPLE_GEOJSON_V2)

    history = await svc.get_version_history(v2.id)
    assert len(history) == 2
    assert history[0].version == 2  # newest first
    assert history[1].version == 1


@pytest.mark.asyncio
async def test_soft_delete_field(db_session: AsyncSession, test_group):
    svc = FieldService(db_session)
    field = await svc.create_field(FieldCreate(name="DeleteMe", group_id=test_group.id))
    await svc.soft_delete(field.id)

    with pytest.raises(Exception):
        await svc.get_by_id(field.id)


# ── API endpoint tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_field(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "API Field", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Field"
    assert data["version"] == 1
    assert data["is_current"] is True


@pytest.mark.asyncio
async def test_api_create_field_with_geometry(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Geo Field",
            "group_id": str(test_group.id),
            "geometry_geojson": SAMPLE_GEOJSON,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["area_acres"] is not None
    assert data["area_acres"] > 0


@pytest.mark.asyncio
async def test_api_get_field_with_geometry(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    # Create
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Detail Field",
            "group_id": str(test_group.id),
            "geometry_geojson": SAMPLE_GEOJSON,
        },
    )
    field_id = create_resp.json()["id"]

    # Get detail
    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry_geojson"] is not None
    assert data["geometry_geojson"]["type"] == "MultiPolygon"


@pytest.mark.asyncio
async def test_api_list_fields(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "List1", "group_id": str(test_group.id)},
    )
    await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "List2", "group_id": str(test_group.id)},
    )

    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_api_update_field(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "OrigName", "group_id": str(test_group.id)},
    )
    field_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/fields/{field_id}",
        headers=_auth(token),
        json={"name": "NewName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


@pytest.mark.asyncio
async def test_api_delete_field(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "ToDelete", "group_id": str(test_group.id)},
    )
    field_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 404
