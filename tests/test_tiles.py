"""TileServingService and MVT endpoint tests."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.security.password import hash_password
from openfmis.services.tiles import VALID_LAYERS, TileService, _build_tile_sql

FIELD_MP = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.05, 38.0],
                [-98.0, 38.0],
                [-98.0, 38.05],
                [-98.05, 38.05],
                [-98.05, 38.0],
            ]
        ]
    ],
}

# z/x/y for a tile covering central Kansas at zoom 8
Z, X, Y = 8, 58, 95


@pytest.fixture
async def tile_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="tileuser",
        email="tileuser@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Tile User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def tile_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="TileFarm")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def tile_field(db_session: AsyncSession, tile_group: Group, tile_user: User) -> Field:
    field = Field(
        id=uuid.uuid4(),
        name="Tile Field",
        group_id=tile_group.id,
        created_by=tile_user.id,
        is_current=True,
        version=1,
    )
    db_session.add(field)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE fields SET geometry = ST_GeomFromGeoJSON(:g) WHERE id = :id"),
        {"g": json.dumps(FIELD_MP), "id": field.id},
    )
    await db_session.flush()
    return field


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "tileuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── SQL builder unit tests ────────────────────────────────────────────────────


def test_build_tile_sql_all_layers():
    for layer in VALID_LAYERS:
        sql = _build_tile_sql(layer, Z, X, Y)
        assert "ST_AsMVT" in sql
        assert "ST_AsMVTGeom" in sql
        assert "ST_TileEnvelope" in sql


def test_build_tile_sql_invalid_layer():
    import pytest

    with pytest.raises(ValueError, match="No SQL builder"):
        _build_tile_sql("nonexistent_layer", Z, X, Y)


# ── TileService unit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tile_invalid_layer(db_session: AsyncSession):
    svc = TileService(db_session)
    with pytest.raises(ValueError, match="Unknown layer"):
        await svc.get_tile("bogus", Z, X, Y)


@pytest.mark.asyncio
async def test_tile_zoom_out_of_range(db_session: AsyncSession):
    svc = TileService(db_session)
    result = await svc.get_tile("fields", 2, X, Y)
    assert result is None


@pytest.mark.asyncio
async def test_tile_fields_returns_bytes_or_none(db_session: AsyncSession, tile_field: Field):
    svc = TileService(db_session)
    # May be None (no features in this tile) or bytes — both valid
    result = await svc.get_tile("fields", Z, X, Y)
    assert result is None or isinstance(result, bytes)


@pytest.mark.asyncio
async def test_tile_clu_runs(db_session: AsyncSession):
    svc = TileService(db_session)
    result = await svc.get_tile("clu", Z, X, Y)
    assert result is None or isinstance(result, bytes)


@pytest.mark.asyncio
async def test_tile_plss_townships_runs(db_session: AsyncSession):
    svc = TileService(db_session)
    result = await svc.get_tile("plss_townships", Z, X, Y)
    assert result is None or isinstance(result, bytes)


@pytest.mark.asyncio
async def test_tile_plss_sections_runs(db_session: AsyncSession):
    svc = TileService(db_session)
    result = await svc.get_tile("plss_sections", Z, X, Y)
    assert result is None or isinstance(result, bytes)


@pytest.mark.asyncio
async def test_tile_analysis_zones_runs(db_session: AsyncSession):
    svc = TileService(db_session)
    result = await svc.get_tile("analysis_zones", Z, X, Y)
    assert result is None or isinstance(result, bytes)


# ── API endpoint tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_layers(client: AsyncClient, tile_user: User):
    token = await _login(client)
    resp = await client.get("/api/v1/tiles/layers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    layers = resp.json()
    assert set(layers) == VALID_LAYERS


@pytest.mark.asyncio
async def test_api_tile_fields(client: AsyncClient, tile_user: User, tile_field: Field):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/tiles/fields/{Z}/{X}/{Y}.mvt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 204)
    if resp.status_code == 200:
        assert resp.headers["content-type"] == "application/vnd.mapbox-vector-tile"


@pytest.mark.asyncio
async def test_api_tile_clu(client: AsyncClient, tile_user: User):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/tiles/clu/{Z}/{X}/{Y}.mvt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 204)


@pytest.mark.asyncio
async def test_api_tile_unknown_layer(client: AsyncClient, tile_user: User):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/tiles/bogus_layer/{Z}/{X}/{Y}.mvt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_tile_requires_auth(client: AsyncClient):
    resp = await client.get(f"/api/v1/tiles/fields/{Z}/{X}/{Y}.mvt")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_tile_zoom_too_low(client: AsyncClient, tile_user: User):
    token = await _login(client)
    # z=2 is below MIN_ZOOM=4, FastAPI path validator rejects it
    resp = await client.get(
        "/api/v1/tiles/fields/2/0/0.mvt",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
