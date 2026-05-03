"""Tests for FieldBoundaryVersion service and API."""

import pytest
import pytest_asyncio

from openfmis.schemas.field_boundary_version import BoundaryVersionCreate
from openfmis.services.field_boundary_version import FieldBoundaryVersionService

SAMPLE_GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-97.0, 40.0],
                [-97.009, 40.0],
                [-97.009, 40.009],
                [-97.0, 40.009],
                [-97.0, 40.0],
            ]
        ]
    ],
}


@pytest_asyncio.fixture
async def bv_svc(db_session):
    return FieldBoundaryVersionService(db_session)


@pytest.mark.asyncio
async def test_create_boundary_version(bv_svc, test_field, test_user):
    data = BoundaryVersionCreate(
        field_id=test_field.id,
        geometry_geojson=SAMPLE_GEOJSON,
        source="import",
    )
    v = await bv_svc.create(data, created_by=test_user.id)
    assert v.id is not None
    assert v.version == 1
    assert v.is_current is True
    assert v.area_acres is not None
    assert v.area_acres > 0


@pytest.mark.asyncio
async def test_version_supersedes(bv_svc, test_field, test_user):
    """Creating a new version marks the old one as non-current."""
    v1 = await bv_svc.create(
        BoundaryVersionCreate(
            field_id=test_field.id, geometry_geojson=SAMPLE_GEOJSON, source="drawn"
        ),
        created_by=test_user.id,
    )
    v2 = await bv_svc.create(
        BoundaryVersionCreate(
            field_id=test_field.id, geometry_geojson=SAMPLE_GEOJSON, source="gps"
        ),
        created_by=test_user.id,
    )
    assert v2.version == 2
    assert v2.is_current is True

    # Refresh v1
    refreshed = await bv_svc.get_by_id(v1.id)
    assert refreshed.is_current is False


@pytest.mark.asyncio
async def test_list_boundary_versions(bv_svc, test_field, test_user):
    for i in range(3):
        await bv_svc.create(
            BoundaryVersionCreate(field_id=test_field.id, geometry_geojson=SAMPLE_GEOJSON),
            created_by=test_user.id,
        )
    items = await bv_svc.list_by_field(test_field.id)
    assert len(items) == 3
    # Should be newest first
    assert items[0].version > items[1].version


@pytest.mark.asyncio
async def test_get_geometry_geojson(bv_svc, test_field, test_user):
    v = await bv_svc.create(
        BoundaryVersionCreate(field_id=test_field.id, geometry_geojson=SAMPLE_GEOJSON),
        created_by=test_user.id,
    )
    geojson = await bv_svc.get_geometry_geojson(v.id)
    assert geojson is not None
    assert geojson["type"] == "MultiPolygon"


# ── API tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_boundary_version(client, auth_headers, test_field):
    resp = await client.post(
        "/api/v1/boundary-versions",
        json={
            "field_id": str(test_field.id),
            "geometry_geojson": SAMPLE_GEOJSON,
            "source": "import",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == 1
    assert data["is_current"] is True


@pytest.mark.asyncio
async def test_api_list_boundary_versions(client, auth_headers, test_field):
    await client.post(
        "/api/v1/boundary-versions",
        json={"field_id": str(test_field.id), "geometry_geojson": SAMPLE_GEOJSON},
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/v1/boundary-versions?field_id={test_field.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_get_boundary_version(client, auth_headers, test_field):
    create_resp = await client.post(
        "/api/v1/boundary-versions",
        json={"field_id": str(test_field.id), "geometry_geojson": SAMPLE_GEOJSON},
        headers=auth_headers,
    )
    vid = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/boundary-versions/{vid}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["geometry_geojson"] is not None
