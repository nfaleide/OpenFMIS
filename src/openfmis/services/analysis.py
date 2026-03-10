"""AnalysisService — manage analysis jobs and zones; drives image extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.satshot import AnalysisJob, AnalysisZone
from openfmis.models.spectral_index import SpectralIndexDefinition
from openfmis.schemas.satshot import JobCreate, ZoneCreate, ZoneUpdate
from openfmis.services.image_extraction import extract_and_compute
from openfmis.services.scene_discovery import SceneDiscoveryService

log = logging.getLogger(__name__)

SCENE_ANALYSIS_CREDIT_COST = 10


class ZoneNotFoundError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


class FieldNotFoundError(Exception):
    pass


# ── Zone service ──────────────────────────────────────────────────────────────


class ZoneService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_zone(
        self, field_id: uuid.UUID, data: ZoneCreate, created_by: uuid.UUID
    ) -> AnalysisZone:
        geom_wkt = None
        if data.geometry_geojson:
            geom_wkt = _geojson_to_wkt(data.geometry_geojson)

        zone = AnalysisZone(
            field_id=field_id,
            name=data.name,
            description=data.description,
            geometry=geom_wkt,
            created_by=created_by,
        )
        self.db.add(zone)
        await self.db.flush()
        await self.db.refresh(zone)
        return zone

    async def get_zone(self, zone_id: uuid.UUID) -> AnalysisZone | None:
        result = await self.db.execute(select(AnalysisZone).where(AnalysisZone.id == zone_id))
        return result.scalar_one_or_none()

    async def list_zones(self, field_id: uuid.UUID) -> list[dict]:
        result = await self.db.execute(
            select(AnalysisZone, ST_AsGeoJSON(AnalysisZone.geometry).label("geojson"))
            .where(AnalysisZone.field_id == field_id)
            .order_by(AnalysisZone.created_at)
        )
        return [_zone_dict(row.AnalysisZone, row.geojson) for row in result]

    async def update_zone(self, zone_id: uuid.UUID, data: ZoneUpdate) -> AnalysisZone:
        zone = await self.get_zone(zone_id)
        if zone is None:
            raise ZoneNotFoundError(str(zone_id))
        if data.name is not None:
            zone.name = data.name
        if data.description is not None:
            zone.description = data.description
        if data.geometry_geojson is not None:
            zone.geometry = _geojson_to_wkt(data.geometry_geojson)
        await self.db.flush()
        await self.db.refresh(zone)
        return zone

    async def delete_zone(self, zone_id: uuid.UUID) -> None:
        zone = await self.get_zone(zone_id)
        if zone is None:
            raise ZoneNotFoundError(str(zone_id))
        await self.db.delete(zone)
        await self.db.flush()

    async def get_zone_geojson(self, zone_id: uuid.UUID) -> dict | None:
        result = await self.db.execute(
            select(ST_AsGeoJSON(AnalysisZone.geometry).label("geojson")).where(
                AnalysisZone.id == zone_id
            )
        )
        row = result.one_or_none()
        if row is None or row.geojson is None:
            return None
        return json.loads(row.geojson)


# ── Analysis service ──────────────────────────────────────────────────────────


class AnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def submit_job(self, data: JobCreate, created_by: uuid.UUID) -> AnalysisJob:
        """Create a pending job and immediately start it in the background."""
        # Validate field exists
        field_result = await self.db.execute(
            select(Field).where(Field.id == data.field_id, Field.deleted_at.is_(None))
        )
        if field_result.scalar_one_or_none() is None:
            raise FieldNotFoundError(str(data.field_id))

        job = AnalysisJob(
            field_id=data.field_id,
            zone_id=data.zone_id,
            scene_id=data.scene_id,
            index_type=data.index_type,
            status="pending",
            created_by=created_by,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        # Fire and forget — runs in background after response returns
        asyncio.create_task(self._run_job(job.id))
        return job

    async def _run_job(self, job_id: uuid.UUID) -> None:
        """Background task: extract bands, compute index, store result."""
        from openfmis.database import async_session_factory

        async with async_session_factory() as db:
            try:
                result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
                job = result.scalar_one_or_none()
                if job is None:
                    return

                job.status = "running"
                await db.flush()

                # Get AOI geometry
                aoi = await self._get_aoi(db, job)
                if aoi is None:
                    job.status = "failed"
                    job.error_message = "No geometry available for field or zone"
                    job.completed_at = datetime.now(UTC)
                    await db.commit()
                    return

                # Look up index definition for formula
                idx_result = await db.execute(
                    select(SpectralIndexDefinition).where(
                        SpectralIndexDefinition.slug == job.index_type
                    )
                )
                idx_def = idx_result.scalar_one_or_none()
                formula = idx_def.formula if idx_def else None
                parameters = idx_def.parameters if idx_def else None
                required_bands = idx_def.required_bands if idx_def else None

                # Get scene assets
                discovery = SceneDiscoveryService(db)
                scene = await discovery.get_scene_by_id(job.scene_id)
                if scene is None:
                    job.status = "failed"
                    job.error_message = f"Scene not found: {job.scene_id}"
                    job.completed_at = datetime.now(UTC)
                    await db.commit()
                    return

                collection = scene.get("collection", "sentinel-2-l2a")
                stats = await extract_and_compute(
                    job.index_type,
                    scene["assets"],
                    aoi,
                    formula=formula,
                    required_bands=required_bands,
                    parameters=parameters,
                    collection=collection,
                )

                job.status = "complete"
                job.result = stats
                job.credits_consumed = SCENE_ANALYSIS_CREDIT_COST
                job.completed_at = datetime.now(UTC)
                await db.commit()
                log.info(
                    "Job %s complete: %s mean=%.3f", job_id, job.index_type, stats.get("mean") or 0
                )

            except Exception as exc:
                log.exception("Job %s failed: %s", job_id, exc)
                try:
                    result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
                    job = result.scalar_one_or_none()
                    if job:
                        job.status = "failed"
                        job.error_message = str(exc)
                        job.completed_at = datetime.now(UTC)
                        await db.commit()
                except Exception:
                    pass

    async def _get_aoi(self, db: AsyncSession, job: AnalysisJob) -> dict | None:
        """Return GeoJSON geometry for the job's zone (if set) or field."""
        if job.zone_id:
            row = await db.execute(
                select(ST_AsGeoJSON(AnalysisZone.geometry).label("g")).where(
                    AnalysisZone.id == job.zone_id
                )
            )
            r = row.one_or_none()
            if r and r.g:
                return json.loads(r.g)

        # Fall back to field geometry
        row = await db.execute(
            select(ST_AsGeoJSON(Field.geometry).label("g")).where(Field.id == job.field_id)
        )
        r = row.one_or_none()
        if r and r.g:
            return json.loads(r.g)
        return None

    async def get_job(self, job_id: uuid.UUID) -> AnalysisJob | None:
        result = await self.db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        field_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnalysisJob], int]:
        stmt = select(AnalysisJob)
        if field_id:
            stmt = stmt.where(AnalysisJob.field_id == field_id)
        if status:
            stmt = stmt.where(AnalysisJob.status == status)

        count_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(
            stmt.order_by(AnalysisJob.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total


# ── Helpers ───────────────────────────────────────────────────────────────────


def _geojson_to_wkt(geojson: dict) -> str:
    """Convert a GeoJSON geometry to PostGIS EWKT (SRID=4326)."""
    geom_type = geojson.get("type", "")
    coords = geojson.get("coordinates", [])
    if geom_type == "Polygon":
        ring_str = ", ".join(f"{x} {y}" for x, y in coords[0])
        return f"SRID=4326;MULTIPOLYGON((({ring_str})))"
    if geom_type == "MultiPolygon":
        parts = []
        for poly in coords:
            ring_str = ", ".join(f"{x} {y}" for x, y in poly[0])
            parts.append(f"(({ring_str}))")
        return f"SRID=4326;MULTIPOLYGON({', '.join(parts)})"
    raise ValueError(f"Unsupported geometry type for zone: {geom_type}")


def _zone_dict(zone: AnalysisZone, geojson: str | None) -> dict:
    return {
        "id": str(zone.id),
        "field_id": str(zone.field_id),
        "name": zone.name,
        "description": zone.description,
        "geometry_geojson": json.loads(geojson) if geojson else None,
        "created_by": str(zone.created_by) if zone.created_by else None,
        "created_at": zone.created_at.isoformat(),
        "updated_at": zone.updated_at.isoformat(),
    }
