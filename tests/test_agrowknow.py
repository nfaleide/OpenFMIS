"""Tests for AgrowKnow API config and job queue."""

from uuid import uuid4

import pytest

from openfmis.services.agrowknow import (
    AgrowKnowConfig,
    AgrowKnowJobQueue,
    DataSource,
    JobStatus,
    JobType,
)


class TestConfig:
    def test_default_sources(self):
        cfg = AgrowKnowConfig()
        sources = cfg.list_sources()
        assert len(sources) == 5
        names = {s["source"] for s in sources}
        assert "cdl" in names
        assert "ssurgo" in names
        assert "weather" in names

    def test_get_source(self):
        cfg = AgrowKnowConfig()
        cdl = cfg.get(DataSource.CDL)
        assert cdl.enabled is True
        assert cdl.base_url is not None

    def test_set_api_key(self):
        cfg = AgrowKnowConfig()
        cfg.set_api_key(DataSource.IMAGERY, "test-key-123")
        assert cfg.get(DataSource.IMAGERY).api_key == "test-key-123"

    def test_enable_disable(self):
        cfg = AgrowKnowConfig()
        cfg.disable(DataSource.CDL)
        assert cfg.get(DataSource.CDL).enabled is False
        cfg.enable(DataSource.CDL)
        assert cfg.get(DataSource.CDL).enabled is True

    def test_update_config(self):
        cfg = AgrowKnowConfig()
        cfg.update(DataSource.WEATHER, rate_limit_rpm=120, custom_param="foo")
        assert cfg.get(DataSource.WEATHER).rate_limit_rpm == 120
        assert cfg.get(DataSource.WEATHER).extra["custom_param"] == "foo"

    def test_serialize_roundtrip(self):
        cfg = AgrowKnowConfig()
        cfg.set_api_key(DataSource.IMAGERY, "key-abc")
        cfg.update(DataSource.CDL, rate_limit_rpm=10)

        data = cfg.to_dict()
        restored = AgrowKnowConfig.from_dict(data)
        assert restored.get(DataSource.IMAGERY).api_key == "key-abc"
        assert restored.get(DataSource.CDL).rate_limit_rpm == 10

    def test_from_dict_ignores_unknown_source(self):
        cfg = AgrowKnowConfig.from_dict({"unknown_source": {"enabled": True}})
        # Should not raise, just skip unknown
        assert len(cfg.list_sources()) == 5


class TestJobQueue:
    def test_submit_job(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.CDL_HISTORY, lat=40.5, lon=-96.5)
        assert job.status == JobStatus.PENDING
        assert job.params["lat"] == 40.5

    def test_get_job(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.SSURGO_PROPERTIES)
        found = q.get(job.id)
        assert found is not None
        assert found.id == job.id

    def test_get_nonexistent(self):
        q = AgrowKnowJobQueue()
        assert q.get(uuid4()) is None

    def test_list_jobs_filtered(self):
        q = AgrowKnowJobQueue()
        field_a = uuid4()
        q.submit(JobType.CDL_HISTORY, field_id=field_a)
        q.submit(JobType.SSURGO_PROPERTIES, field_id=field_a)
        q.submit(JobType.CDL_HISTORY, field_id=uuid4())

        cdl_jobs = q.list_jobs(job_type=JobType.CDL_HISTORY)
        assert len(cdl_jobs) == 2

        field_a_jobs = q.list_jobs(field_id=field_a)
        assert len(field_a_jobs) == 2

    def test_cancel_pending(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.CDL_HISTORY)
        assert q.cancel(job.id) is True
        assert q.get(job.id).status == JobStatus.CANCELLED

    def test_cancel_nonexistent(self):
        q = AgrowKnowJobQueue()
        assert q.cancel(uuid4()) is False


@pytest.mark.asyncio
class TestJobExecution:
    async def test_run_missing_params_fails(self):
        """CDL job without lat/lon should fail."""
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.CDL_HISTORY)
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED
        assert "lat" in result.error

    async def test_run_nonexistent_raises(self):
        q = AgrowKnowJobQueue()
        with pytest.raises(ValueError, match="not found"):
            await q.run_job(uuid4())

    async def test_run_non_pending_raises(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.CDL_HISTORY)
        q.cancel(job.id)
        with pytest.raises(ValueError, match="not pending"):
            await q.run_job(job.id)

    async def test_drone_job_missing_content(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.DRONE_IMPORT, field_id=uuid4())
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED
        assert "file_content" in result.error

    async def test_ssurgo_missing_params(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.SSURGO_PROPERTIES)
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED

    async def test_weather_missing_params(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.WEATHER_SUMMARY, lat=40.5)
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED

    async def test_gdd_missing_params(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.GDD_ACCUMULATION)
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED

    async def test_batch_missing_params(self):
        q = AgrowKnowJobQueue()
        job = q.submit(JobType.MULTI_FIELD_BATCH)
        result = await q.run_job(job.id)
        assert result.status == JobStatus.FAILED

    async def test_drone_import_via_queue(self):
        """End-to-end drone import through the job queue."""
        import struct
        import tempfile

        # Build minimal TIFF
        data = bytearray()
        data += b"II"
        data += struct.pack("<H", 42)
        data += struct.pack("<I", 8)
        data += struct.pack("<H", 3)
        for tag, val in [(256, 100), (257, 100), (277, 3)]:
            data += struct.pack("<H", tag)
            data += struct.pack("<H", 3)
            data += struct.pack("<I", 1)
            data += struct.pack("<I", val)
        data += struct.pack("<I", 0)

        field_id = uuid4()
        q = AgrowKnowJobQueue()
        with tempfile.TemporaryDirectory() as tmpdir:
            job = q.submit(
                JobType.DRONE_IMPORT,
                field_id=field_id,
                file_content=bytes(data),
                filename="test.tif",
                storage_dir=tmpdir,
            )
            result = await q.run_job(job.id)
            # The basic TIFF lacks bounds, so validation may fail — that's OK
            assert result.status == JobStatus.COMPLETED
            assert result.result is not None

    async def test_process_pending(self):
        """process_pending runs multiple jobs."""
        q = AgrowKnowJobQueue()
        q.submit(JobType.CDL_HISTORY)  # Will fail (no params)
        q.submit(JobType.SSURGO_PROPERTIES)  # Will fail (no params)

        results = await q.process_pending()
        assert len(results) == 2
        assert all(j.status == JobStatus.FAILED for j in results)

        # All processed, nothing pending
        remaining = q.list_jobs(status=JobStatus.PENDING)
        assert len(remaining) == 0
