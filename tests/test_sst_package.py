"""SST package parser + import tests."""

import io
import os
import uuid
import zipfile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.services.sst_package import (
    SSTClient,
    SSTFarm,
    SSTField,
    SSTImportService,
    SSTPackageData,
    _clean_uuid,
    parse_sst_package,
)

# ── Helper to build minimal .shp/.shx/.dbf for testing ──────────────────


def _make_minimal_shapefile(tmpdir: str, name: str, wkt_polygon: str = ""):
    """Create a minimal shapefile triplet in tmpdir.

    This creates valid-enough .shp/.shx/.dbf files that fiona can open.
    For simplicity we use fiona to write them.
    """
    import fiona
    from fiona.crs import from_epsg
    from shapely import wkt
    from shapely.geometry import mapping

    shp_path = os.path.join(tmpdir, f"{name}.shp")
    schema = {"geometry": "Polygon", "properties": {"name": "str"}}
    with fiona.open(
        shp_path, "w", driver="ESRI Shapefile", schema=schema, crs=from_epsg(4326)
    ) as dst:
        if wkt_polygon:
            geom = wkt.loads(wkt_polygon)
            dst.write({"geometry": mapping(geom), "properties": {"name": name}})
    return shp_path


# ── Unit tests: _clean_uuid ─────────────────────────────────────────────


class TestCleanUUID:
    def test_strips_braces(self):
        uid = str(uuid.uuid4())
        assert _clean_uuid(f"{{{uid}}}") == uid

    def test_strips_whitespace(self):
        uid = str(uuid.uuid4())
        assert _clean_uuid(f"  {uid}  ") == uid

    def test_plain_uuid(self):
        uid = str(uuid.uuid4())
        assert _clean_uuid(uid) == uid


# ── Parser: not a ZIP ───────────────────────────────────────────────────


class TestParserValidation:
    def test_not_a_zip(self):
        with pytest.raises(ValidationError, match="not a valid ZIP"):
            parse_sst_package(b"not a zip file at all")

    def test_zip_without_mdb(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "no mdb here")
        with pytest.raises(ValidationError, match="missing dtumeta.mdb"):
            parse_sst_package(buf.getvalue())


# ── Import service (uses constructed SSTPackageData, no MDB needed) ─────


def _sample_package() -> SSTPackageData:
    """Build a sample parsed SST package for import tests."""
    client_id = str(uuid.uuid4())
    farm_id = str(uuid.uuid4())
    field1_id = str(uuid.uuid4())
    field2_id = str(uuid.uuid4())

    return SSTPackageData(
        clients=[
            SSTClient(
                clientid=client_id,
                name="Test Grower",
                farms=[
                    SSTFarm(
                        farmid=farm_id,
                        clientid=client_id,
                        name="Home Farm",
                        fields=[
                            SSTField(
                                fieldid=field1_id,
                                farmid=farm_id,
                                name="North 40",
                                boundary_geojson={
                                    "type": "MultiPolygon",
                                    "coordinates": [
                                        [
                                            [
                                                [-96.8, 40.8],
                                                [-96.8, 40.81],
                                                [-96.79, 40.81],
                                                [-96.79, 40.8],
                                                [-96.8, 40.8],
                                            ]
                                        ]
                                    ],
                                },
                            ),
                            SSTField(
                                fieldid=field2_id,
                                farmid=farm_id,
                                name="South 80",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_import_sst_creates_hierarchy(db_session: AsyncSession):
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(_sample_package())

    assert result.groups_created == 1
    assert result.regions_created == 1
    assert result.fields_created == 2
    assert result.mappings_created == 4  # group + region + 2 fields
    assert result.skipped == 0


@pytest.mark.asyncio
async def test_import_sst_into_existing_group(db_session: AsyncSession, test_group):
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(_sample_package(), target_group_id=test_group.id)

    assert result.groups_created == 0
    assert result.regions_created == 1
    assert result.fields_created == 2


@pytest.mark.asyncio
async def test_import_sst_idempotent(db_session: AsyncSession):
    pkg = _sample_package()
    svc = SSTImportService(db_session)

    r1 = await svc.import_sst_package(pkg)
    assert r1.fields_created == 2

    r2 = await svc.import_sst_package(pkg)
    assert r2.fields_created == 0
    assert r2.skipped >= 2


@pytest.mark.asyncio
async def test_import_sst_field_no_name(db_session: AsyncSession, test_group):
    pkg = SSTPackageData(
        clients=[
            SSTClient(
                clientid=str(uuid.uuid4()),
                name="C1",
                farms=[
                    SSTFarm(
                        farmid=str(uuid.uuid4()),
                        clientid="x",
                        name="F1",
                        fields=[
                            SSTField(
                                fieldid=str(uuid.uuid4()),
                                farmid="x",
                                name="",  # empty name
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(pkg, target_group_id=test_group.id)

    assert result.fields_created == 0
    assert result.skipped == 1
    assert any("no name" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_import_sst_with_geometry(db_session: AsyncSession):
    """Fields with boundary_geojson should get geometry stored."""
    from sqlalchemy import select

    from openfmis.models.field import Field

    pkg = _sample_package()
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(pkg)

    assert result.fields_created == 2

    # Fetch the field that had geometry
    stmt = select(Field).where(Field.name == "North 40")
    fields = (await db_session.execute(stmt)).scalars().all()
    assert len(fields) == 1


@pytest.mark.asyncio
async def test_import_sst_target_group_not_found(db_session: AsyncSession):
    svc = SSTImportService(db_session)
    fake_id = uuid.uuid4()
    with pytest.raises(ValidationError, match="Target group not found"):
        await svc.import_sst_package(_sample_package(), target_group_id=fake_id)


@pytest.mark.asyncio
async def test_import_sst_empty_package(db_session: AsyncSession):
    pkg = SSTPackageData(clients=[])
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(pkg)

    assert result.groups_created == 0
    assert result.fields_created == 0


@pytest.mark.asyncio
async def test_import_sst_warnings_propagate(db_session: AsyncSession):
    pkg = SSTPackageData(
        clients=[
            SSTClient(
                clientid=str(uuid.uuid4()),
                name="C1",
                farms=[
                    SSTFarm(
                        farmid=str(uuid.uuid4()),
                        clientid="x",
                        name="F1",
                        fields=[
                            SSTField(
                                fieldid=str(uuid.uuid4()),
                                farmid="x",
                                name="BadField",
                                warnings=["Boundary shapefile could not be read"],
                            ),
                        ],
                    ),
                ],
            ),
        ],
        warnings=["Parser warning"],
    )
    svc = SSTImportService(db_session)
    result = await svc.import_sst_package(pkg)

    assert any("Parser warning" in w for w in result.warnings)
    assert any("could not be read" in w for w in result.warnings)


# ── API test ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_import_sst_not_a_zip(client, auth_headers):
    """API should reject non-ZIP uploads."""

    resp = await client.post(
        "/api/v1/import/sst-package",
        files={"file": ("test.sst", b"not a zip", "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
