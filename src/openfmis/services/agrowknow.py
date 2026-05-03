"""AgrowKnow API configuration and job queue.

Orchestrates external agronomic data retrieval (CDL, SSURGO, weather,
imagery) through a unified config + async job queue.  Each data source
has its own service module; this module manages credentials, rate limits,
and background job dispatch / status tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class DataSource(StrEnum):
    """Supported external data sources."""

    CDL = "cdl"
    SSURGO = "ssurgo"
    WEATHER = "weather"
    IMAGERY = "imagery"
    DRONE = "drone"


@dataclass
class SourceConfig:
    """Per-source API configuration."""

    source: DataSource
    enabled: bool = True
    api_key: str | None = None
    base_url: str | None = None
    rate_limit_rpm: int = 60
    timeout_seconds: int = 30
    extra: dict[str, Any] = field(default_factory=dict)


# Default configs — USDA services are free / no key required
_DEFAULT_CONFIGS: dict[DataSource, SourceConfig] = {
    DataSource.CDL: SourceConfig(
        source=DataSource.CDL,
        base_url="https://nassgeodata.gmu.edu/axis2/services/CDLService",
        rate_limit_rpm=30,
    ),
    DataSource.SSURGO: SourceConfig(
        source=DataSource.SSURGO,
        base_url="https://SDMDataAccess.sc.egov.usda.gov/Tabular/post.rest",
        rate_limit_rpm=30,
    ),
    DataSource.WEATHER: SourceConfig(
        source=DataSource.WEATHER,
        base_url="https://archive-api.open-meteo.com/v1/archive",
        rate_limit_rpm=60,
    ),
    DataSource.IMAGERY: SourceConfig(
        source=DataSource.IMAGERY,
        enabled=False,  # Requires Satshot plugin
    ),
    DataSource.DRONE: SourceConfig(
        source=DataSource.DRONE,
        enabled=True,
    ),
}


class AgrowKnowConfig:
    """Manages API configuration for all data sources."""

    def __init__(self) -> None:
        self._configs: dict[DataSource, SourceConfig] = {
            k: SourceConfig(
                source=v.source,
                enabled=v.enabled,
                api_key=v.api_key,
                base_url=v.base_url,
                rate_limit_rpm=v.rate_limit_rpm,
                timeout_seconds=v.timeout_seconds,
                extra=dict(v.extra),
            )
            for k, v in _DEFAULT_CONFIGS.items()
        }

    def get(self, source: DataSource) -> SourceConfig:
        return self._configs[source]

    def update(self, source: DataSource, **kwargs: Any) -> SourceConfig:
        """Update configuration for a source."""
        cfg = self._configs[source]
        for k, v in kwargs.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                cfg.extra[k] = v
        return cfg

    def set_api_key(self, source: DataSource, key: str) -> None:
        self._configs[source].api_key = key

    def enable(self, source: DataSource) -> None:
        self._configs[source].enabled = True

    def disable(self, source: DataSource) -> None:
        self._configs[source].enabled = False

    def list_sources(self) -> list[dict[str, Any]]:
        """Return summary of all configured sources."""
        return [
            {
                "source": cfg.source.value,
                "enabled": cfg.enabled,
                "has_api_key": cfg.api_key is not None,
                "base_url": cfg.base_url,
                "rate_limit_rpm": cfg.rate_limit_rpm,
            }
            for cfg in self._configs.values()
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize config for storage."""
        return {
            src.value: {
                "enabled": cfg.enabled,
                "api_key": cfg.api_key,
                "base_url": cfg.base_url,
                "rate_limit_rpm": cfg.rate_limit_rpm,
                "timeout_seconds": cfg.timeout_seconds,
                "extra": cfg.extra,
            }
            for src, cfg in self._configs.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgrowKnowConfig:
        """Restore config from stored dict."""
        config = cls()
        for src_str, vals in data.items():
            try:
                source = DataSource(src_str)
            except ValueError:
                continue
            if source in config._configs:
                for k, v in vals.items():
                    if k == "extra":
                        config._configs[source].extra.update(v)
                    elif hasattr(config._configs[source], k):
                        setattr(config._configs[source], k, v)
        return config


# ---------------------------------------------------------------------------
# Job Queue
# ---------------------------------------------------------------------------


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    """Types of agronomic data jobs."""

    CDL_HISTORY = "cdl_history"
    SSURGO_PROPERTIES = "ssurgo_properties"
    WEATHER_SUMMARY = "weather_summary"
    GDD_ACCUMULATION = "gdd_accumulation"
    DRONE_IMPORT = "drone_import"
    MULTI_FIELD_BATCH = "multi_field_batch"


@dataclass
class AgrowKnowJob:
    """A queued or completed data-retrieval job."""

    id: UUID
    job_type: JobType
    status: JobStatus
    field_id: UUID | None = None
    group_id: UUID | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    progress_pct: int = 0


class AgrowKnowJobQueue:
    """In-memory async job queue for agronomic data retrieval.

    For production, back this with a persistent store (DB table or Redis).
    This implementation is suitable for single-process dev / QGIS plugin use.
    """

    def __init__(self, config: AgrowKnowConfig | None = None) -> None:
        self.config = config or AgrowKnowConfig()
        self._jobs: dict[UUID, AgrowKnowJob] = {}
        self._running: set[UUID] = set()
        self._max_concurrent = 4

    def submit(
        self,
        job_type: JobType,
        field_id: UUID | None = None,
        group_id: UUID | None = None,
        **params: Any,
    ) -> AgrowKnowJob:
        """Submit a new job to the queue."""
        job = AgrowKnowJob(
            id=uuid4(),
            job_type=job_type,
            status=JobStatus.PENDING,
            field_id=field_id,
            group_id=group_id,
            params=params,
            created_at=time.time(),
        )
        self._jobs[job.id] = job
        log.info("Job %s submitted: %s", job.id, job_type.value)
        return job

    def get(self, job_id: UUID) -> AgrowKnowJob | None:
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        field_id: UUID | None = None,
    ) -> list[AgrowKnowJob]:
        """List jobs, optionally filtered."""
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if job_type is not None:
            jobs = [j for j in jobs if j.job_type == job_type]
        if field_id is not None:
            jobs = [j for j in jobs if j.field_id == field_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def cancel(self, job_id: UUID) -> bool:
        """Cancel a pending job. Returns False if already running/done."""
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status != JobStatus.PENDING:
            return False
        job.status = JobStatus.CANCELLED
        return True

    async def run_job(self, job_id: UUID) -> AgrowKnowJob:
        """Execute a single job. Called by the dispatcher or directly."""
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        if job.status != JobStatus.PENDING:
            raise ValueError(f"Job {job_id} is {job.status.value}, not pending")

        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        self._running.add(job_id)

        try:
            result = await self._execute(job)
            job.result = result
            job.status = JobStatus.COMPLETED
            job.progress_pct = 100
        except Exception as exc:
            job.error = str(exc)
            job.status = JobStatus.FAILED
            log.error("Job %s failed: %s", job_id, exc)
        finally:
            job.completed_at = time.time()
            self._running.discard(job_id)

        return job

    async def process_pending(self, max_jobs: int = 10) -> list[AgrowKnowJob]:
        """Process up to max_jobs pending jobs concurrently."""
        pending = [j for j in self._jobs.values() if j.status == JobStatus.PENDING]
        pending.sort(key=lambda j: j.created_at)
        batch = pending[:max_jobs]

        if not batch:
            return []

        tasks = [self.run_job(j.id) for j in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        completed = []
        for r in results:
            if isinstance(r, AgrowKnowJob):
                completed.append(r)
        return completed

    async def _execute(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Dispatch job to the appropriate handler."""
        handlers = {
            JobType.CDL_HISTORY: self._run_cdl,
            JobType.SSURGO_PROPERTIES: self._run_ssurgo,
            JobType.WEATHER_SUMMARY: self._run_weather,
            JobType.GDD_ACCUMULATION: self._run_gdd,
            JobType.DRONE_IMPORT: self._run_drone,
            JobType.MULTI_FIELD_BATCH: self._run_batch,
        }
        handler = handlers.get(job.job_type)
        if handler is None:
            raise ValueError(f"Unknown job type: {job.job_type}")
        return await handler(job)

    async def _run_cdl(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run CDL crop history job."""
        from openfmis.services.cdl import get_crop_history, summarize_crop_history

        lat = job.params.get("lat")
        lon = job.params.get("lon")
        years = job.params.get("years", 5)
        if lat is None or lon is None:
            raise ValueError("CDL job requires lat and lon params")

        current_year = datetime.now().year
        year_range = list(range(current_year - years, current_year))
        history = await get_crop_history(lat, lon, year_range)
        summary = summarize_crop_history(history)
        return {
            "history": [
                {"year": h.year, "crop_code": h.crop_code, "crop_name": h.crop_name}
                for h in history
            ],
            "summary": summary,
        }

    async def _run_ssurgo(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run SSURGO soil properties job."""
        from openfmis.services.ssurgo import get_soil_properties, summarize_soil

        lat = job.params.get("lat")
        lon = job.params.get("lon")
        if lat is None or lon is None:
            raise ValueError("SSURGO job requires lat and lon params")

        components = await get_soil_properties(lat, lon)
        summary = summarize_soil(components)
        return {
            "components": len(components),
            "summary": summary,
        }

    async def _run_weather(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run weather summary job."""
        from openfmis.services.weather import get_weather, summarize_weather

        lat = job.params.get("lat")
        lon = job.params.get("lon")
        start_date = job.params.get("start_date")
        end_date = job.params.get("end_date")
        if not all([lat, lon, start_date, end_date]):
            raise ValueError("Weather job requires lat, lon, start_date, end_date")

        records = await get_weather(lat, lon, start_date, end_date)
        summary = summarize_weather(records)
        return {
            "days": len(records),
            "summary": summary,
        }

    async def _run_gdd(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run GDD accumulation job."""
        from openfmis.services.weather import (
            accumulate_gdd,
            get_weather,
        )

        lat = job.params.get("lat")
        lon = job.params.get("lon")
        start_date = job.params.get("start_date")
        end_date = job.params.get("end_date")
        base_temp = job.params.get("base_temp", 50.0)
        upper_temp = job.params.get("upper_temp", 86.0)
        if not all([lat, lon, start_date, end_date]):
            raise ValueError("GDD job requires lat, lon, start_date, end_date")

        records = await get_weather(lat, lon, start_date, end_date)
        gdd_data = accumulate_gdd(records, base_temp, upper_temp)
        return {
            "days": len(gdd_data),
            "total_gdd": gdd_data[-1]["cumulative"] if gdd_data else 0.0,
            "data": gdd_data,
        }

    async def _run_drone(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run drone imagery import job."""
        from openfmis.services.drone_import import import_drone_image

        file_content = job.params.get("file_content")
        filename = job.params.get("filename", "drone.tif")
        field_id = job.field_id
        if file_content is None or field_id is None:
            raise ValueError("Drone job requires file_content and field_id")

        result = await import_drone_image(
            file_content,
            filename,
            field_id,
            storage_dir=job.params.get("storage_dir", "/tmp/drone_imagery"),
        )
        return {
            "success": result.success,
            "dataset_id": str(result.dataset_id) if result.dataset_id else None,
            "storage_path": result.storage_path,
            "error": result.error,
            "warnings": result.warnings,
        }

    async def _run_batch(self, job: AgrowKnowJob) -> dict[str, Any]:
        """Run a multi-field batch of sub-jobs."""
        sub_type_str = job.params.get("sub_type")
        field_coords = job.params.get("field_coords", [])
        if not sub_type_str or not field_coords:
            raise ValueError("Batch job requires sub_type and field_coords")

        sub_type = JobType(sub_type_str)
        results = []
        for i, coord in enumerate(field_coords):
            sub_job = self.submit(
                sub_type,
                field_id=coord.get("field_id"),
                **{k: v for k, v in coord.items() if k != "field_id"},
            )
            completed = await self.run_job(sub_job.id)
            results.append(
                {
                    "field_id": str(coord.get("field_id")),
                    "status": completed.status.value,
                    "result": completed.result,
                    "error": completed.error,
                }
            )
            job.progress_pct = int((i + 1) / len(field_coords) * 100)

        succeeded = sum(1 for r in results if r["status"] == "completed")
        return {
            "total": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
            "results": results,
        }
