"""Tests for VRAPrescriptionService."""

import uuid
from datetime import UTC, datetime

import pytest

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.satshot import AnalysisJob
from openfmis.services.vra_prescription import JobNotReadyError, VRAPrescriptionService

FIELD_WKT = "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"


@pytest.fixture
async def completed_job(db_session):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="VRA Field",
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
        scene_id="S2_VRA_001",
        index_type="ndvi",
        status="complete",
        result={
            "mean": 0.65,
            "min": 0.2,
            "max": 0.9,
            "std": 0.15,
            "p10": 0.35,
            "p90": 0.85,
            "pixel_count": 10000,
            "valid_pixel_count": 9500,
            "nodata_fraction": 0.05,
        },
        completed_at=datetime.now(UTC),
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest.fixture
async def pending_job(db_session):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="Pending Field",
        geometry=FIELD_WKT,
        area_acres=50.0,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add(field)
    await db_session.flush()
    job = AnalysisJob(field_id=field.id, scene_id="S2_PEND", index_type="ndvi", status="pending")
    db_session.add(job)
    await db_session.flush()
    return job


class TestVRAPrescriptionService:
    async def test_generate_tgt(self, db_session, completed_job):
        svc = VRAPrescriptionService(db_session)
        result = await svc.generate_tgt(
            completed_job.id,
            [
                {"zone_name": "Low", "min_value": 0.2, "max_value": 0.5, "target_rate": 200},
                {"zone_name": "High", "min_value": 0.5, "max_value": 0.9, "target_rate": 100},
            ],
        )
        assert result["type"] == "tgt"
        assert len(result["zones"]) == 2

    async def test_generate_fodm(self, db_session, completed_job):
        svc = VRAPrescriptionService(db_session)
        result = await svc.generate_fodm(
            completed_job.id, base_rate=150, rate_adjustment=50, num_zones=3
        )
        assert result["type"] == "fodm"
        assert len(result["zones"]) == 3

    async def test_generate_bmp(self, db_session, completed_job):
        svc = VRAPrescriptionService(db_session)
        result = await svc.generate_bmp(
            completed_job.id, breakpoints=[0.4, 0.7], rates=[200, 150, 100]
        )
        assert result["type"] == "bmp"
        assert len(result["zones"]) == 3

    async def test_bmp_wrong_rates_length(self, db_session, completed_job):
        svc = VRAPrescriptionService(db_session)
        with pytest.raises(ValueError, match="rates length"):
            await svc.generate_bmp(completed_job.id, breakpoints=[0.4], rates=[200])

    async def test_pending_job_raises(self, db_session, pending_job):
        svc = VRAPrescriptionService(db_session)
        with pytest.raises(JobNotReadyError):
            await svc.generate_tgt(
                pending_job.id,
                [
                    {"zone_name": "Z", "min_value": 0, "max_value": 1, "target_rate": 100},
                ],
            )

    async def test_job_not_found(self, db_session):
        svc = VRAPrescriptionService(db_session)
        with pytest.raises(ValueError, match="Job not found"):
            await svc.generate_fodm(uuid.uuid4(), base_rate=100, rate_adjustment=50)
