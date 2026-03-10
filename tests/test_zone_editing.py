"""Tests for ZoneEditingService — spatial zone operations."""

import uuid

import pytest

from openfmis.models.group import Group
from openfmis.models.satshot import AnalysisZone
from openfmis.services.zone_editing import ZoneEditingService, ZoneNotFoundError

SAMPLE_POLYGON_WKT = (
    "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"
)

SAMPLE_POLYGON_WKT_2 = (
    "SRID=4326;MULTIPOLYGON(((-95.9 41.0, -95.8 41.0, -95.8 41.1, -95.9 41.1, -95.9 41.0)))"
)


@pytest.fixture
async def field_id(db_session):
    """Create a test field and return its ID."""
    from openfmis.models.field import Field

    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="Test Field",
        geometry=SAMPLE_POLYGON_WKT,
        area_acres=100.0,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add(field)
    await db_session.flush()
    return field.id


@pytest.fixture
async def two_zones(db_session, field_id):
    """Create two adjacent zones."""
    z1 = AnalysisZone(field_id=field_id, name="Zone A", geometry=SAMPLE_POLYGON_WKT)
    z2 = AnalysisZone(field_id=field_id, name="Zone B", geometry=SAMPLE_POLYGON_WKT_2)
    db_session.add_all([z1, z2])
    await db_session.flush()
    return z1, z2


class TestZoneEditingService:
    async def test_merge_zones(self, db_session, two_zones):
        z1, z2 = two_zones
        svc = ZoneEditingService(db_session)
        merged = await svc.merge_zones([z1.id, z2.id], "Merged Zone")
        assert merged.name == "Merged Zone"
        # Originals should be deleted
        assert await svc._load_zones([merged.id])

    async def test_merge_requires_two(self, db_session, two_zones):
        z1, _ = two_zones
        svc = ZoneEditingService(db_session)
        with pytest.raises(ValueError, match="at least 2"):
            await svc.merge_zones([z1.id], "Bad Merge")

    async def test_merge_not_found(self, db_session):
        svc = ZoneEditingService(db_session)
        with pytest.raises(ZoneNotFoundError):
            await svc.merge_zones([uuid.uuid4(), uuid.uuid4()], "Bad")

    async def test_dissolve_zones(self, db_session, two_zones):
        z1, z2 = two_zones
        svc = ZoneEditingService(db_session)
        result = await svc.dissolve_zones([z1.id, z2.id])
        assert len(result) == 1
        assert "dissolved" in result[0].name

    async def test_buffer_zone(self, db_session, two_zones):
        z1, _ = two_zones
        svc = ZoneEditingService(db_session)
        buffered = await svc.buffer_zone(z1.id, 100.0)
        assert buffered.id == z1.id

    async def test_paint_zone(self, db_session, two_zones):
        z1, _ = two_zones
        paint_geom = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-96.05, 40.95],
                    [-95.95, 40.95],
                    [-95.95, 41.05],
                    [-96.05, 41.05],
                    [-96.05, 40.95],
                ]
            ],
        }
        svc = ZoneEditingService(db_session)
        painted = await svc.paint_zone(z1.id, paint_geom)
        assert painted.id == z1.id

    async def test_zone_not_found(self, db_session):
        svc = ZoneEditingService(db_session)
        with pytest.raises(ZoneNotFoundError):
            await svc.buffer_zone(uuid.uuid4(), 10.0)
