"""Export service tests — GeoJSON, Shapefile, KML, CSV."""

import io
import uuid
import zipfile

import fiona
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.region import Region
from openfmis.models.user import User
from openfmis.schemas.field import FieldCreate
from openfmis.security.password import hash_password
from openfmis.services.export_ import ExportService
from openfmis.services.field import FieldService

SAMPLE_MP = {
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


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="ExportTestFarm")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_region(db_session: AsyncSession, test_group: Group) -> Region:
    region = Region(id=uuid.uuid4(), name="Test Farm", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()
    return region


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="exportuser",
        email="export@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Export User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def fields_in_db(
    db_session: AsyncSession, test_group: Group, test_region: Region, test_user: User
) -> list[uuid.UUID]:
    """Create three fields with geometry and return their IDs."""
    svc = FieldService(db_session)
    names = ["North 40", "South 80", "East Quarter"]
    ids = []
    for name in names:
        field = await svc.create_field(
            FieldCreate(
                name=name,
                group_id=test_group.id,
                region_id=test_region.id,
                geometry_geojson=SAMPLE_MP,
            ),
            created_by=test_user.id,
        )
        ids.append(field.id)
    return ids


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "exportuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── GeoJSON export ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_geojson_all(db_session: AsyncSession, test_group: Group, fields_in_db: list):
    svc = ExportService(db_session)
    fc = await svc.export_geojson(group_id=test_group.id)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 3
    for feat in fc["features"]:
        assert feat["geometry"]["type"] == "MultiPolygon"
        assert "name" in feat["properties"]
        assert "area_acres" in feat["properties"]


@pytest.mark.asyncio
async def test_export_geojson_by_field_ids(db_session: AsyncSession, fields_in_db: list):
    svc = ExportService(db_session)
    fc = await svc.export_geojson(field_ids=fields_in_db[:2])
    assert len(fc["features"]) == 2


@pytest.mark.asyncio
async def test_export_geojson_empty_group(db_session: AsyncSession):
    svc = ExportService(db_session)
    fc = await svc.export_geojson(group_id=uuid.uuid4())
    assert fc["type"] == "FeatureCollection"
    assert fc["features"] == []


@pytest.mark.asyncio
async def test_export_geojson_no_geometry_field(
    db_session: AsyncSession, test_group: Group, test_region: Region, test_user: User
):
    """Fields with no geometry should still appear in export with null geometry."""
    svc_field = FieldService(db_session)
    await svc_field.create_field(
        FieldCreate(name="No Geom Field", group_id=test_group.id, region_id=test_region.id),
        created_by=test_user.id,
    )
    svc = ExportService(db_session)
    fc = await svc.export_geojson(group_id=test_group.id)
    null_geom = [f for f in fc["features"] if f["geometry"] is None]
    assert len(null_geom) == 1


# ── Shapefile export ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_shapefile_returns_zip(
    db_session: AsyncSession, test_group: Group, fields_in_db: list
):
    svc = ExportService(db_session)
    zip_bytes = await svc.export_shapefile(group_id=test_group.id)
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert any(n.endswith(".shp") for n in names)
        assert any(n.endswith(".dbf") for n in names)


@pytest.mark.asyncio
async def test_export_shapefile_readable(
    db_session: AsyncSession, test_group: Group, fields_in_db: list
):
    """The exported shapefile should be openable by fiona."""
    import os
    import tempfile

    svc = ExportService(db_session)
    zip_bytes = await svc.export_shapefile(group_id=test_group.id)

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmpdir)
        shp_files = [f for f in os.listdir(tmpdir) if f.endswith(".shp")]
        assert len(shp_files) == 1
        shp_path = os.path.join(tmpdir, shp_files[0])

        with fiona.open(shp_path) as src:
            features = list(src)
            assert len(features) == 3
            for feat in features:
                # Shapefiles don't distinguish Polygon/MultiPolygon internally;
                # fiona may read single-part MultiPolygons back as Polygon
                assert feat.geometry["type"] in ("Polygon", "MultiPolygon")
                assert feat.properties["name"]


@pytest.mark.asyncio
async def test_export_shapefile_by_field_ids(db_session: AsyncSession, fields_in_db: list):
    import os
    import tempfile

    svc = ExportService(db_session)
    zip_bytes = await svc.export_shapefile(field_ids=fields_in_db[:1])

    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmpdir)
        shp_path = os.path.join(tmpdir, [f for f in os.listdir(tmpdir) if f.endswith(".shp")][0])
        with fiona.open(shp_path) as src:
            assert len(list(src)) == 1


# ── KML export ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_kml_returns_bytes(
    db_session: AsyncSession, test_group: Group, fields_in_db: list
):
    svc = ExportService(db_session)
    kml_bytes = await svc.export_kml(group_id=test_group.id)
    assert len(kml_bytes) > 0
    assert b"<?xml" in kml_bytes


@pytest.mark.asyncio
async def test_export_kml_readable(db_session: AsyncSession, test_group: Group, fields_in_db: list):
    import xml.etree.ElementTree as ET

    svc = ExportService(db_session)
    kml_bytes = await svc.export_kml(group_id=test_group.id)

    # Parse as XML — must be valid
    root = ET.fromstring(kml_bytes)
    ns = "{http://www.opengis.net/kml/2.2}"
    placemarks = list(root.iter(f"{ns}Placemark"))
    assert len(placemarks) == 3
    for pm in placemarks:
        name_el = pm.find(f"{ns}name")
        assert name_el is not None and name_el.text


# ── CSV export ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_csv_columns(db_session: AsyncSession, test_group: Group, fields_in_db: list):
    import csv as csv_mod

    svc = ExportService(db_session)
    csv_text = await svc.export_csv(group_id=test_group.id)
    reader = csv_mod.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 3
    assert "wkt" in reader.fieldnames  # type: ignore[operator]
    assert "name" in reader.fieldnames  # type: ignore[operator]
    for row in rows:
        assert row["wkt"].startswith("MULTIPOLYGON")


@pytest.mark.asyncio
async def test_export_csv_by_field_ids(db_session: AsyncSession, fields_in_db: list):
    import csv as csv_mod

    svc = ExportService(db_session)
    csv_text = await svc.export_csv(field_ids=fields_in_db[:2])
    reader = csv_mod.DictReader(io.StringIO(csv_text))
    assert len(list(reader)) == 2


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_export_geojson(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/export/geojson?group_id={test_group.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/geo+json")
    fc = resp.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 3


@pytest.mark.asyncio
async def test_api_export_geojson_by_field_ids(
    client: AsyncClient, test_user: User, fields_in_db: list
):
    token = await _login(client)
    ids_param = ",".join(str(fid) for fid in fields_in_db[:2])
    resp = await client.get(
        f"/api/v1/export/geojson?field_ids={ids_param}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["features"]) == 2


@pytest.mark.asyncio
async def test_api_export_shapefile(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/export/shapefile?group_id={test_group.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert len(resp.content) > 0
    # Verify it's a valid zip
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert any(n.endswith(".shp") for n in zf.namelist())


@pytest.mark.asyncio
async def test_api_export_kml(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    import xml.etree.ElementTree as ET

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/export/kml?group_id={test_group.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "kml" in resp.headers["content-type"]
    # Must be valid XML
    root = ET.fromstring(resp.content)
    assert root is not None


@pytest.mark.asyncio
async def test_api_export_csv(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    import csv as csv_mod

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/export/csv?group_id={test_group.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "csv" in resp.headers["content-type"]
    reader = csv_mod.DictReader(io.StringIO(resp.text))
    assert len(list(reader)) == 3


@pytest.mark.asyncio
async def test_api_export_requires_auth(client: AsyncClient, test_group: Group):
    resp = await client.get(f"/api/v1/export/geojson?group_id={test_group.id}")
    assert resp.status_code == 401


# ── Export link tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_link_create_and_consume(
    db_session: AsyncSession, test_group: Group, fields_in_db: list, test_user: User
):
    """Create an export link, then consume it — full round-trip."""
    svc = ExportService(db_session)
    link = await svc.create_export_link(
        format="geojson",
        created_by=test_user.id,
        group_id=test_group.id,
        expires_in_hours=1,
    )
    assert link.hash
    assert len(link.hash) == 64  # SHA-256 hex
    assert link.format == "geojson"
    assert link.download_count == 0

    # Consume it
    content, content_type, filename = await svc.consume_export_link(link.hash)
    assert content_type == "application/geo+json"
    assert filename == "fields.geojson"
    assert '"FeatureCollection"' in content

    # Download count should have incremented
    refreshed = await svc.get_export_link(link.hash)
    assert refreshed.download_count == 1


@pytest.mark.asyncio
async def test_export_link_expired(
    db_session: AsyncSession, test_group: Group, fields_in_db: list, test_user: User
):
    """Expired links should raise NotFoundError."""
    from openfmis.exceptions import NotFoundError

    svc = ExportService(db_session)
    link = await svc.create_export_link(
        format="geojson",
        created_by=test_user.id,
        group_id=test_group.id,
        expires_in_hours=1,
    )
    # Manually expire it
    from datetime import UTC, datetime, timedelta

    link.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    with pytest.raises(NotFoundError, match="expired"):
        await svc.get_export_link(link.hash)


@pytest.mark.asyncio
async def test_export_link_max_downloads(
    db_session: AsyncSession, test_group: Group, fields_in_db: list, test_user: User
):
    """Links with max_downloads should stop working after limit."""
    from openfmis.exceptions import NotFoundError

    svc = ExportService(db_session)
    link = await svc.create_export_link(
        format="csv",
        created_by=test_user.id,
        group_id=test_group.id,
        max_downloads=1,
    )
    # First download succeeds
    await svc.consume_export_link(link.hash)

    # Second should fail
    with pytest.raises(NotFoundError, match="download limit"):
        await svc.consume_export_link(link.hash)


@pytest.mark.asyncio
async def test_export_link_with_field_ids(
    db_session: AsyncSession, fields_in_db: list, test_user: User
):
    """Links can filter by specific field IDs."""
    import json

    svc = ExportService(db_session)
    link = await svc.create_export_link(
        format="geojson",
        created_by=test_user.id,
        field_ids=fields_in_db[:1],
    )
    assert "field_ids" in link.filters
    assert len(link.filters["field_ids"]) == 1

    content, _, _ = await svc.consume_export_link(link.hash)
    fc = json.loads(content)
    assert len(fc["features"]) == 1


@pytest.mark.asyncio
async def test_export_link_not_found(db_session: AsyncSession):
    """Nonexistent hash should raise NotFoundError."""
    from openfmis.exceptions import NotFoundError

    svc = ExportService(db_session)
    with pytest.raises(NotFoundError, match="not found"):
        await svc.get_export_link("0" * 64)


@pytest.mark.asyncio
async def test_api_create_export_link(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    """POST /export/links creates a valid link."""
    token = await _login(client)
    resp = await client.post(
        "/api/v1/export/links",
        json={"format": "geojson", "group_id": str(test_group.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert len(data["hash"]) == 64
    assert data["format"] == "geojson"


@pytest.mark.asyncio
async def test_api_download_export_link(
    client: AsyncClient, test_user: User, test_group: Group, fields_in_db: list
):
    """GET /export/links/{hash} downloads without auth."""
    token = await _login(client)
    # Create link
    create_resp = await client.post(
        "/api/v1/export/links",
        json={"format": "geojson", "group_id": str(test_group.id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    link_hash = create_resp.json()["hash"]

    # Download without auth
    dl_resp = await client.get(f"/api/v1/export/links/{link_hash}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"].startswith("application/geo+json")
    fc = dl_resp.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 3


@pytest.mark.asyncio
async def test_api_download_export_link_not_found(client: AsyncClient):
    """GET /export/links/{bad_hash} returns 404."""
    resp = await client.get(f"/api/v1/export/links/{'0' * 64}")
    assert resp.status_code == 404
