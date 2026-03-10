"""Tests for ImageryExportService."""

import uuid
from datetime import UTC, datetime

import pytest

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.satshot import AnalysisJob
from openfmis.services.imagery_export import ImageryExportService

FIELD_WKT = "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"


@pytest.fixture
async def completed_job(db_session):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="Export Field",
        geometry=FIELD_WKT,
        area_acres=100.0,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add(field)
    await db_session.flush()

    job = AnalysisJob(
        field_id=field.id,
        scene_id="S2_EXP_001",
        index_type="ndvi",
        status="complete",
        result={
            "mean": 0.65,
            "min": 0.2,
            "max": 0.9,
            "std": 0.15,
            "pixel_count": 10000,
            "valid_pixel_count": 9500,
            "nodata_fraction": 0.05,
        },
        completed_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()
    return job


class TestImageryExportService:
    async def test_export_geojson_no_zones(self, db_session, completed_job):
        svc = ImageryExportService(db_session)
        result = await svc.export_geojson(completed_job.id)
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 1

    async def test_export_geojson_with_zones(self, db_session, completed_job):
        svc = ImageryExportService(db_session)
        zones = [
            {"zone_name": "Low", "min_value": 0.2, "max_value": 0.5, "geometry": None},
            {"zone_name": "High", "min_value": 0.5, "max_value": 0.9, "geometry": None},
        ]
        result = await svc.export_geojson(completed_job.id, zones=zones)
        assert len(result["features"]) == 2

    async def test_export_csv(self, db_session, completed_job):
        svc = ImageryExportService(db_session)
        csv = await svc.export_csv(completed_job.id)
        assert "zone_name" in csv
        assert "ndvi" in csv

    async def test_export_csv_with_zones(self, db_session, completed_job):
        svc = ImageryExportService(db_session)
        zones = [
            {
                "zone_name": "Z1",
                "min_value": 0.2,
                "max_value": 0.5,
                "target_rate": 200,
                "unit": "lbs/ac",
            }
        ]
        csv = await svc.export_csv(completed_job.id, zones=zones)
        lines = csv.strip().split("\n")
        assert len(lines) == 2  # header + 1 zone

    async def test_export_kml(self, db_session, completed_job):
        svc = ImageryExportService(db_session)
        kml = await svc.export_kml(completed_job.id)
        assert "<?xml" in kml
        assert "kml" in kml

    async def test_job_not_found(self, db_session):
        svc = ImageryExportService(db_session)
        with pytest.raises(ValueError, match="Job not found"):
            await svc.export_geojson(uuid.uuid4())
