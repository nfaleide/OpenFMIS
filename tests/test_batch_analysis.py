"""Tests for BatchAnalysisService."""

import uuid

import pytest

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.services.batch_analysis import BatchAnalysisService

FIELD_WKT_1 = (
    "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"
)
FIELD_WKT_2 = (
    "SRID=4326;MULTIPOLYGON(((-95.8 41.0, -95.7 41.0, -95.7 41.1, -95.8 41.1, -95.8 41.0)))"
)


@pytest.fixture
async def two_fields(db_session):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    f1 = Field(
        name="Batch Field 1",
        geometry=FIELD_WKT_1,
        area_acres=80,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    f2 = Field(
        name="Batch Field 2",
        geometry=FIELD_WKT_2,
        area_acres=120,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add_all([f1, f2])
    await db_session.flush()
    return f1, f2


class TestBatchAnalysisService:
    async def test_create_batch(self, db_session, two_fields, test_user):
        f1, f2 = two_fields
        svc = BatchAnalysisService(db_session)
        batch = await svc.create_batch(
            [f1.id, f2.id], "SCENE_BATCH", "ndvi", created_by=test_user.id
        )
        assert batch.status == "running"
        assert len(batch.job_ids) == 2

    async def test_batch_dedup_jobs(self, db_session, two_fields, test_user):
        f1, f2 = two_fields
        svc = BatchAnalysisService(db_session)
        b1 = await svc.create_batch([f1.id], "SCENE_DD", "ndvi", created_by=test_user.id)
        b2 = await svc.create_batch([f1.id], "SCENE_DD", "ndvi", created_by=test_user.id)
        # Second batch should reuse existing job
        assert b2.job_ids[0] == b1.job_ids[0]

    async def test_get_batch_status(self, db_session, two_fields, test_user):
        f1, f2 = two_fields
        svc = BatchAnalysisService(db_session)
        batch = await svc.create_batch(
            [f1.id, f2.id], "SCENE_STAT", "ndvi", created_by=test_user.id
        )
        status = await svc.get_batch_status(batch.id)
        assert status["total_fields"] == 2
        assert status["scene_id"] == "SCENE_STAT"

    async def test_batch_not_found(self, db_session):
        svc = BatchAnalysisService(db_session)
        with pytest.raises(ValueError, match="Batch not found"):
            await svc.get_batch_status(uuid.uuid4())

    async def test_list_batches(self, db_session, two_fields, test_user):
        f1, f2 = two_fields
        svc = BatchAnalysisService(db_session)
        await svc.create_batch([f1.id], "SCENE_L1", "ndvi", created_by=test_user.id)
        await svc.create_batch([f2.id], "SCENE_L2", "evi", created_by=test_user.id)
        batches = await svc.list_batches(created_by=test_user.id)
        assert len(batches) >= 2
