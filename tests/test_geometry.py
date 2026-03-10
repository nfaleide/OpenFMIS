"""Geometry spatial operations tests."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.schemas.field import FieldCreate
from openfmis.services.field import FieldService
from openfmis.services.geometry import GeometryService

# Sample GeoJSON — a simple square polygon in Kansas
SQUARE_GEOJSON = {
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

# A larger square that overlaps SQUARE_GEOJSON
LARGE_SQUARE_GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.01, 37.99],
                [-98.01, 38.02],
                [-97.98, 38.02],
                [-97.98, 37.99],
                [-98.01, 37.99],
            ]
        ]
    ],
}

# A second non-overlapping square
DISJOINT_GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-99.0, 39.0],
                [-99.0, 39.01],
                [-98.99, 39.01],
                [-98.99, 39.0],
                [-99.0, 39.0],
            ]
        ]
    ],
}

# A point (for type detection)
POINT_GEOJSON = {
    "type": "Point",
    "coordinates": [-98.0, 38.0],
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
    group = Group(id=uuid.uuid4(), name="GeoCo")
    db_session.add(group)
    await db_session.flush()
    return group


# ── Unit tests via GeometryService ─────────────────────────────


@pytest.mark.asyncio
async def test_validate_valid_geometry(db_session: AsyncSession):
    svc = GeometryService(db_session)
    is_valid, reason = await svc.validate(SQUARE_GEOJSON)
    assert is_valid is True
    assert reason is None


@pytest.mark.asyncio
async def test_calculate_area(db_session: AsyncSession):
    svc = GeometryService(db_session)
    area_acres, area_sq_m = await svc.calculate_area(SQUARE_GEOJSON)
    assert area_acres > 0
    assert area_sq_m > 0
    # ~0.01 degree square in Kansas ≈ 200-300 acres
    assert 100 < area_acres < 500


@pytest.mark.asyncio
async def test_bbox_area(db_session: AsyncSession):
    svc = GeometryService(db_session)
    min_lon, min_lat, max_lon, max_lat, area_acres = await svc.calculate_bbox_area(SQUARE_GEOJSON)
    assert min_lon == pytest.approx(-98.0, abs=0.001)
    assert min_lat == pytest.approx(38.0, abs=0.001)
    assert max_lon == pytest.approx(-97.99, abs=0.001)
    assert max_lat == pytest.approx(38.01, abs=0.001)
    assert area_acres > 0


@pytest.mark.asyncio
async def test_geometry_type_multipolygon(db_session: AsyncSession):
    svc = GeometryService(db_session)
    geom_type, num = await svc.get_type(SQUARE_GEOJSON)
    assert geom_type == "MULTIPOLYGON"
    assert num == 1


@pytest.mark.asyncio
async def test_geometry_type_point(db_session: AsyncSession):
    svc = GeometryService(db_session)
    geom_type, num = await svc.get_type(POINT_GEOJSON)
    assert geom_type == "POINT"
    assert num == 1


@pytest.mark.asyncio
async def test_centroid(db_session: AsyncSession):
    svc = GeometryService(db_session)
    lon, lat = await svc.centroid(SQUARE_GEOJSON)
    assert lon == pytest.approx(-97.995, abs=0.001)
    assert lat == pytest.approx(38.005, abs=0.001)


@pytest.mark.asyncio
async def test_union(db_session: AsyncSession):
    svc = GeometryService(db_session)
    result = await svc.union([SQUARE_GEOJSON, LARGE_SQUARE_GEOJSON])
    assert result["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_clip(db_session: AsyncSession):
    svc = GeometryService(db_session)
    # Clip LARGE by SQUARE — should give area of SQUARE
    result = await svc.clip(LARGE_SQUARE_GEOJSON, SQUARE_GEOJSON)
    assert result["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_hole(db_session: AsyncSession):
    svc = GeometryService(db_session)
    # Punch SQUARE-sized hole in LARGE — result should be LARGE minus SQUARE
    result = await svc.hole(LARGE_SQUARE_GEOJSON, SQUARE_GEOJSON)
    assert result["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_buffer(db_session: AsyncSession):
    svc = GeometryService(db_session)
    result = await svc.buffer(POINT_GEOJSON, 1000)  # 1km buffer
    assert result["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_find_intersecting_fields(db_session: AsyncSession, test_group):
    # Create a field with geometry
    fsvc = FieldService(db_session)
    await fsvc.create_field(
        FieldCreate(name="Overlap Field", group_id=test_group.id, geometry_geojson=SQUARE_GEOJSON)
    )
    await fsvc.create_field(
        FieldCreate(name="Far Field", group_id=test_group.id, geometry_geojson=DISJOINT_GEOJSON)
    )

    gsvc = GeometryService(db_session)
    results = await gsvc.find_intersecting_fields(LARGE_SQUARE_GEOJSON)
    assert len(results) == 1
    assert results[0]["field_name"] == "Overlap Field"
    assert results[0]["intersection_area_acres"] > 0


# ── API endpoint tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_validate(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/validate",
        headers=_auth(token),
        json={"geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True


@pytest.mark.asyncio
async def test_api_area(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/area",
        headers=_auth(token),
        json={"geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["area_acres"] > 0
    assert data["area_sq_meters"] > 0


@pytest.mark.asyncio
async def test_api_bbox(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/bbox",
        headers=_auth(token),
        json={"geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_longitude"] < data["max_longitude"]
    assert data["area_acres"] > 0


@pytest.mark.asyncio
async def test_api_type(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/type",
        headers=_auth(token),
        json={"geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    assert resp.json()["geometry_type"] == "MULTIPOLYGON"


@pytest.mark.asyncio
async def test_api_centroid(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/centroid",
        headers=_auth(token),
        json={"geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert -98.0 < data["longitude"] < -97.99
    assert 38.0 < data["latitude"] < 38.01


@pytest.mark.asyncio
async def test_api_union(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/union",
        headers=_auth(token),
        json={"geometries": [SQUARE_GEOJSON, LARGE_SQUARE_GEOJSON]},
    )
    assert resp.status_code == 200
    assert resp.json()["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_api_clip(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/clip",
        headers=_auth(token),
        json={"geometry": LARGE_SQUARE_GEOJSON, "clip_geometry": SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    assert resp.json()["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_api_buffer(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/geometry/buffer",
        headers=_auth(token),
        json={"geometry": POINT_GEOJSON, "distance_meters": 500},
    )
    assert resp.status_code == 200
    assert resp.json()["type"] in ("Polygon", "MultiPolygon")


@pytest.mark.asyncio
async def test_api_intersections(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    # Create a field with geometry via API
    await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Intersect Target",
            "group_id": str(test_group.id),
            "geometry_geojson": SQUARE_GEOJSON,
        },
    )

    resp = await client.post(
        "/api/v1/geometry/intersections",
        headers=_auth(token),
        json={"geometry": LARGE_SQUARE_GEOJSON},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
