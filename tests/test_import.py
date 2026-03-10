"""Import service tests — Shapefile, GeoJSON, KML, CSV."""

import io
import json
import os
import tempfile
import uuid
import zipfile

import fiona
import fiona.transform
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.security.password import hash_password
from openfmis.services.import_ import ImportService

# ── Shared GeoJSON geometry ────────────────────────────────────────────────

KANSAS_FIELD_MP = {
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

KANSAS_FIELD_POLY = {
    "type": "Polygon",
    "coordinates": [
        [
            [-98.0, 38.0],
            [-98.0, 38.01],
            [-97.99, 38.01],
            [-97.99, 38.0],
            [-98.0, 38.0],
        ]
    ],
}


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="ImportTestFarm")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="importuser",
        email="import@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Import User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "importuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── Helpers to build test files ────────────────────────────────────────────


def _make_geojson_bytes(features: list[dict]) -> bytes:
    fc = {"type": "FeatureCollection", "features": features}
    return json.dumps(fc).encode()


def _make_shapefile_zip(features: list[dict], name_field: str = "name") -> bytes:
    """Write features to an ESRI Shapefile and return a zip as bytes."""
    schema = {
        "geometry": "MultiPolygon",
        "properties": {name_field: "str"},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        shp_path = os.path.join(tmpdir, "test_fields.shp")
        with fiona.open(
            shp_path, "w", driver="ESRI Shapefile", schema=schema, crs="EPSG:4326"
        ) as dst:
            for feat in features:
                dst.write(feat)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(tmpdir):
                zf.write(os.path.join(tmpdir, fname), fname)
        return buf.getvalue()


def _make_kml_bytes(placemarks: list[dict]) -> bytes:
    """Build a minimal KML document from a list of {name, mp_geojson} dicts."""
    import xml.etree.ElementTree as ET

    ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", ns)
    kml = ET.Element(f"{{{ns}}}kml")
    doc = ET.SubElement(kml, f"{{{ns}}}Document")

    for pm_data in placemarks:
        pm = ET.SubElement(doc, f"{{{ns}}}Placemark")
        ET.SubElement(pm, f"{{{ns}}}name").text = pm_data.get("name", "Test Field")
        # Write a simple Polygon element
        poly_el = ET.SubElement(pm, f"{{{ns}}}Polygon")
        outer = ET.SubElement(poly_el, f"{{{ns}}}outerBoundaryIs")
        lr = ET.SubElement(outer, f"{{{ns}}}LinearRing")
        geom = pm_data.get(
            "coordinates",
            [[-98.0, 38.0], [-98.0, 38.01], [-97.99, 38.01], [-97.99, 38.0], [-98.0, 38.0]],
        )
        ET.SubElement(lr, f"{{{ns}}}coordinates").text = " ".join(
            f"{lon},{lat},0" for lon, lat in geom
        )

    buf = io.BytesIO()
    ET.ElementTree(kml).write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


def _make_csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    import csv as csv_mod

    buf = io.StringIO()
    writer = csv_mod.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode()


# ── GeoJSON import tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_geojson_multipolygon(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    content = _make_geojson_bytes(
        [
            {
                "type": "Feature",
                "geometry": KANSAS_FIELD_MP,
                "properties": {"name": "North 40"},
            }
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=content,
        filename="fields.geojson",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1
    assert result.skipped == 0
    assert len(result.field_ids) == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_import_geojson_polygon_normalised(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    """Polygon geometries should be normalised to MultiPolygon."""
    content = _make_geojson_bytes(
        [
            {
                "type": "Feature",
                "geometry": KANSAS_FIELD_POLY,
                "properties": {"field_name": "South 80"},
            },
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=content,
        filename="fields.geojson",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_import_geojson_multiple_features(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    content = _make_geojson_bytes(
        [
            {"type": "Feature", "geometry": KANSAS_FIELD_MP, "properties": {"name": f"Field {i}"}}
            for i in range(5)
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=content,
        filename="fields.geojson",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 5
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_import_geojson_point_skipped(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    """Point geometries are not polygons — should be skipped."""
    content = _make_geojson_bytes(
        [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-98.0, 38.0]},
                "properties": {"name": "A Point"},
            }
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=content,
        filename="fields.geojson",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 0
    assert result.skipped == 1
    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_import_geojson_name_fallback(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    """When no name property found, falls back to 'Field N'."""
    content = _make_geojson_bytes(
        [
            {"type": "Feature", "geometry": KANSAS_FIELD_MP, "properties": {}},
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=content,
        filename="fields.geojson",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1


# ── Shapefile import tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_shapefile_zip(db_session: AsyncSession, test_group: Group, test_user: User):
    zip_bytes = _make_shapefile_zip(
        [
            {"geometry": KANSAS_FIELD_MP, "properties": {"name": "SHP Field 1"}},
            {"geometry": KANSAS_FIELD_MP, "properties": {"name": "SHP Field 2"}},
        ]
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=zip_bytes,
        filename="fields.zip",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 2
    assert result.skipped == 0
    assert result.errors == []


@pytest.mark.asyncio
async def test_import_shapefile_custom_name_field(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    zip_bytes = _make_shapefile_zip(
        [{"geometry": KANSAS_FIELD_MP, "properties": {"parcel": "Far North"}}],
        name_field="parcel",
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=zip_bytes,
        filename="fields.zip",
        group_id=test_group.id,
        created_by=test_user.id,
        name_field="parcel",
    )
    assert result.created == 1


@pytest.mark.asyncio
async def test_import_shapefile_invalid_zip(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=b"not a zip",
        filename="bad.zip",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 0
    assert len(result.errors) >= 1


# ── KML import tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_kml(db_session: AsyncSession, test_group: Group, test_user: User):
    kml_bytes = _make_kml_bytes([{"name": "KML Field"}])
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=kml_bytes,
        filename="fields.kml",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1
    assert result.skipped == 0


# ── CSV import tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_csv_wkt(db_session: AsyncSession, test_group: Group, test_user: User):
    from shapely.geometry import shape

    wkt = shape(KANSAS_FIELD_MP).wkt
    csv_bytes = _make_csv_bytes(
        [{"name": "CSV WKT Field", "wkt": wkt}],
        columns=["name", "wkt"],
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=csv_bytes,
        filename="fields.csv",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_import_csv_lat_lon(db_session: AsyncSession, test_group: Group, test_user: User):
    csv_bytes = _make_csv_bytes(
        [{"name": "Point Field", "lat": "38.005", "lon": "-97.995"}],
        columns=["name", "lat", "lon"],
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=csv_bytes,
        filename="points.csv",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 1


@pytest.mark.asyncio
async def test_import_csv_missing_geometry_column(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    csv_bytes = _make_csv_bytes(
        [{"name": "No Geom", "value": "42"}],
        columns=["name", "value"],
    )
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=csv_bytes,
        filename="nogeom.csv",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 0
    assert len(result.errors) == 1


# ── Unsupported format test ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_unsupported_format(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    svc = ImportService(db_session)
    result = await svc.import_vector(
        file_content=b"data",
        filename="fields.gpkg",
        group_id=test_group.id,
        created_by=test_user.id,
    )
    assert result.created == 0
    assert result.skipped == 0
    assert len(result.errors) == 1
    assert ".gpkg" in result.errors[0]


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_import_geojson(client: AsyncClient, test_user: User, test_group: Group):
    token = await _login(client)
    content = _make_geojson_bytes(
        [
            {
                "type": "Feature",
                "geometry": KANSAS_FIELD_MP,
                "properties": {"name": "API GeoJSON Field"},
            },
        ]
    )
    resp = await client.post(
        "/api/v1/import/vector",
        headers={"Authorization": f"Bearer {token}"},
        data={"group_id": str(test_group.id)},
        files={"file": ("fields.geojson", content, "application/geo+json")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1
    assert data["skipped"] == 0
    assert len(data["field_ids"]) == 1


@pytest.mark.asyncio
async def test_api_import_shapefile(client: AsyncClient, test_user: User, test_group: Group):
    token = await _login(client)
    zip_bytes = _make_shapefile_zip(
        [
            {"geometry": KANSAS_FIELD_MP, "properties": {"name": "API SHP Field"}},
        ]
    )
    resp = await client.post(
        "/api/v1/import/vector",
        headers={"Authorization": f"Bearer {token}"},
        data={"group_id": str(test_group.id)},
        files={"file": ("fields.zip", zip_bytes, "application/zip")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 1


@pytest.mark.asyncio
async def test_api_import_requires_auth(client: AsyncClient, test_group: Group):
    content = _make_geojson_bytes(
        [
            {"type": "Feature", "geometry": KANSAS_FIELD_MP, "properties": {}},
        ]
    )
    resp = await client.post(
        "/api/v1/import/vector",
        data={"group_id": str(test_group.id)},
        files={"file": ("fields.geojson", content, "application/geo+json")},
    )
    assert resp.status_code == 401
