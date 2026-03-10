"""BatchAnalysisService — multi-field and area-based analysis queries."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from geoalchemy2.functions import ST_Intersects
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.batch_analysis import BatchAnalysis
from openfmis.models.field import Field
from openfmis.models.plss import PLSSSection, PLSSTownship
from openfmis.models.satshot import AnalysisJob

log = logging.getLogger(__name__)


class BatchAnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_batch(
        self,
        field_ids: list[uuid.UUID],
        scene_id: str,
        index_type: str,
        created_by: uuid.UUID | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> BatchAnalysis:
        """Create a batch analysis with individual jobs per field."""
        batch = BatchAnalysis(
            name=name or f"Batch {index_type.upper()} - {scene_id[:20]}",
            description=description,
            field_ids=[str(fid) for fid in field_ids],
            scene_id=scene_id,
            index_type=index_type,
            status="pending",
            created_by=created_by,
        )
        self.db.add(batch)
        await self.db.flush()

        # Create an AnalysisJob for each field
        job_ids = []
        for fid in field_ids:
            # Skip if job already exists
            existing = await self.db.execute(
                select(AnalysisJob.id).where(
                    AnalysisJob.field_id == fid,
                    AnalysisJob.scene_id == scene_id,
                    AnalysisJob.index_type == index_type,
                    AnalysisJob.status.in_(["pending", "running", "complete"]),
                )
            )
            existing_id = existing.scalar_one_or_none()
            if existing_id:
                job_ids.append(str(existing_id))
                continue

            job = AnalysisJob(
                field_id=fid,
                scene_id=scene_id,
                index_type=index_type,
                status="pending",
                created_by=created_by,
            )
            self.db.add(job)
            await self.db.flush()
            await self.db.refresh(job)
            job_ids.append(str(job.id))

        batch.job_ids = job_ids
        batch.status = "running"
        await self.db.flush()
        await self.db.refresh(batch)
        return batch

    async def create_batch_by_area(
        self,
        geometry_geojson: dict,
        scene_id: str,
        index_type: str,
        created_by: uuid.UUID | None = None,
        name: str | None = None,
    ) -> BatchAnalysis:
        """Find all fields intersecting a geometry and create a batch."""

        result = await self.db.execute(
            select(Field.id).where(
                Field.deleted_at.is_(None),
                Field.is_current.is_(True),
                Field.geometry.is_not(None),
                func.ST_Intersects(
                    Field.geometry,
                    func.ST_SetSRID(
                        func.ST_GeomFromGeoJSON(str(geometry_geojson).replace("'", '"')), 4326
                    ),
                ),
            )
        )
        field_ids = [row.id for row in result]
        if not field_ids:
            raise ValueError("No fields found intersecting the provided geometry")

        return await self.create_batch(
            field_ids,
            scene_id,
            index_type,
            created_by=created_by,
            name=name or f"Area analysis - {len(field_ids)} fields",
        )

    async def create_batch_by_plss(
        self,
        plss_id: uuid.UUID,
        plss_type: str,  # "township" or "section"
        scene_id: str,
        index_type: str,
        created_by: uuid.UUID | None = None,
    ) -> BatchAnalysis:
        """Find all fields within a PLSS township or section and create a batch."""
        if plss_type == "township":
            plss_result = await self.db.execute(
                select(PLSSTownship).where(PLSSTownship.id == plss_id)
            )
        else:
            plss_result = await self.db.execute(
                select(PLSSSection).where(PLSSSection.id == plss_id)
            )
        plss_record = plss_result.scalar_one_or_none()
        if plss_record is None:
            raise ValueError(f"PLSS {plss_type} not found: {plss_id}")

        # Find fields intersecting the PLSS boundary
        result = await self.db.execute(
            select(Field.id).where(
                Field.deleted_at.is_(None),
                Field.is_current.is_(True),
                Field.geometry.is_not(None),
                ST_Intersects(Field.geometry, plss_record.geom),
            )
        )
        field_ids = [row.id for row in result]
        if not field_ids:
            raise ValueError(f"No fields found within PLSS {plss_type} {plss_id}")

        label = getattr(plss_record, "label", str(plss_id))
        return await self.create_batch(
            field_ids,
            scene_id,
            index_type,
            created_by=created_by,
            name=f"{label} - {len(field_ids)} fields",
        )

    async def get_batch(self, batch_id: uuid.UUID) -> BatchAnalysis | None:
        result = await self.db.execute(select(BatchAnalysis).where(BatchAnalysis.id == batch_id))
        return result.scalar_one_or_none()

    async def get_batch_status(self, batch_id: uuid.UUID) -> dict:
        """Get batch status with per-field job results for comparison."""
        batch = await self.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"Batch not found: {batch_id}")

        if not batch.job_ids:
            return {"batch_id": str(batch.id), "status": batch.status, "fields": []}

        job_uuids = [uuid.UUID(jid) for jid in batch.job_ids]
        result = await self.db.execute(select(AnalysisJob).where(AnalysisJob.id.in_(job_uuids)))
        jobs = list(result.scalars().all())

        # Get field names
        field_uuids = [j.field_id for j in jobs]
        field_result = await self.db.execute(
            select(Field.id, Field.name).where(Field.id.in_(field_uuids))
        )
        field_names = {row.id: row.name for row in field_result}

        fields = []
        all_complete = True
        any_failed = False
        for job in jobs:
            r = job.result or {}
            fields.append(
                {
                    "field_id": str(job.field_id),
                    "field_name": field_names.get(job.field_id, str(job.field_id)),
                    "job_id": str(job.id),
                    "status": job.status,
                    "mean": r.get("mean"),
                    "min": r.get("min"),
                    "max": r.get("max"),
                    "std": r.get("std"),
                }
            )
            if job.status != "complete":
                all_complete = False
            if job.status == "failed":
                any_failed = True

        # Update batch status
        if all_complete and fields:
            batch.status = "complete"
            batch.completed_at = datetime.now(UTC)
            # Compute aggregate summary
            means = [f["mean"] for f in fields if f["mean"] is not None]
            batch.summary = {
                "total_fields": len(fields),
                "completed": sum(1 for f in fields if f["status"] == "complete"),
                "failed": sum(1 for f in fields if f["status"] == "failed"),
                "avg_mean": sum(means) / len(means) if means else None,
                "min_mean": min(means) if means else None,
                "max_mean": max(means) if means else None,
            }
            await self.db.flush()
        elif any_failed:
            batch.status = "partial"
            await self.db.flush()

        return {
            "batch_id": str(batch.id),
            "name": batch.name,
            "scene_id": batch.scene_id,
            "index_type": batch.index_type,
            "status": batch.status,
            "total_fields": len(fields),
            "summary": batch.summary,
            "fields": fields,
        }

    async def list_batches(
        self,
        created_by: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BatchAnalysis]:
        stmt = select(BatchAnalysis)
        if created_by:
            stmt = stmt.where(BatchAnalysis.created_by == created_by)
        result = await self.db.execute(
            stmt.order_by(BatchAnalysis.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all())
