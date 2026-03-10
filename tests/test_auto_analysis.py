"""Tests for AutoAnalysisService — scene matching and job queuing."""

from datetime import UTC

import pytest

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.satshot import SceneRecord
from openfmis.services.auto_analysis import AutoAnalysisService

FIELD_WKT = "SRID=4326;MULTIPOLYGON(((-96.0 41.0, -95.9 41.0, -95.9 41.1, -96.0 41.1, -96.0 41.0)))"
SCENE_WKT = "SRID=4326;MULTIPOLYGON(((-97.0 40.0, -95.0 40.0, -95.0 42.0, -97.0 42.0, -97.0 40.0)))"


@pytest.fixture
async def setup_field_and_scene(db_session):
    group = Group(name="Test Group")
    db_session.add(group)
    await db_session.flush()

    field = Field(
        name="Auto Test Field",
        geometry=FIELD_WKT,
        area_acres=100.0,
        version=1,
        is_current=True,
        group_id=group.id,
    )
    db_session.add(field)

    from datetime import datetime

    scene = SceneRecord(
        scene_id="S2A_TEST_001",
        collection="sentinel-2-l2a",
        acquired_at=datetime(2025, 6, 15, tzinfo=UTC),
        cloud_cover=5.0,
        assets={"nir": "https://example.com/nir.tif", "red": "https://example.com/red.tif"},
        footprint=SCENE_WKT,
    )
    db_session.add(scene)
    await db_session.flush()
    return field, scene


class TestAutoAnalysisService:
    async def test_match_scene_to_fields(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        matches = await svc.match_scene_to_fields(scene.scene_id)
        assert len(matches) >= 1
        assert any(m["field_id"] == str(field.id) for m in matches)

    async def test_queue_jobs(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        jobs = await svc.queue_jobs_for_scene(scene.scene_id, index_type="ndvi")
        assert len(jobs) >= 1
        assert all(j.status == "pending" for j in jobs)

    async def test_dedup_jobs(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        _jobs1 = await svc.queue_jobs_for_scene(scene.scene_id, index_type="ndvi")
        jobs2 = await svc.queue_jobs_for_scene(scene.scene_id, index_type="ndvi")
        assert len(jobs2) == 0  # Already queued

    async def test_queue_specific_fields(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        jobs = await svc.queue_jobs_for_scene(
            scene.scene_id, index_type="evi", field_ids=[field.id]
        )
        assert len(jobs) == 1

    async def test_get_pending_jobs(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        await svc.queue_jobs_for_scene(scene.scene_id, index_type="gndvi")
        pending = await svc.get_pending_jobs()
        assert len(pending) >= 1

    async def test_scene_match_summary(self, db_session, setup_field_and_scene):
        field, scene = setup_field_and_scene
        svc = AutoAnalysisService(db_session)
        summary = await svc.get_scene_match_summary(scene.scene_id)
        assert summary["matching_fields"] >= 1
        assert summary["scene_id"] == scene.scene_id
