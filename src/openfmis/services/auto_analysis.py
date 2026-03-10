"""AutoAnalysisService — match new scenes to subscribed fields and queue analysis jobs."""

from __future__ import annotations

import logging
import uuid

from geoalchemy2.functions import ST_Intersects
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.satshot import AnalysisJob, SceneRecord

log = logging.getLogger(__name__)

DEFAULT_INDEX = "ndvi"


class AutoAnalysisService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def match_scene_to_fields(self, scene_id: str) -> list[dict]:
        """Find all active fields whose geometry intersects the scene footprint.

        Returns list of {field_id, field_name, area_acres}.
        """
        result = await self.db.execute(
            select(Field.id, Field.name, Field.area_acres)
            .join(SceneRecord, SceneRecord.scene_id == scene_id)
            .where(
                Field.deleted_at.is_(None),
                Field.is_current.is_(True),
                Field.geometry.is_not(None),
                SceneRecord.footprint.is_not(None),
                ST_Intersects(Field.geometry, SceneRecord.footprint),
            )
        )
        return [
            {"field_id": str(row.id), "field_name": row.name, "area_acres": row.area_acres}
            for row in result
        ]

    async def queue_jobs_for_scene(
        self,
        scene_id: str,
        index_type: str = DEFAULT_INDEX,
        created_by: uuid.UUID | None = None,
        field_ids: list[uuid.UUID] | None = None,
    ) -> list[AnalysisJob]:
        """Create pending analysis jobs for all fields matching a scene.

        If field_ids is provided, only queue for those fields.
        Skips fields that already have a job for this scene+index combination.
        """
        if field_ids:
            matches = [{"field_id": str(fid)} for fid in field_ids]
        else:
            matches = await self.match_scene_to_fields(scene_id)

        jobs = []
        for match in matches:
            fid = uuid.UUID(match["field_id"])

            # Skip duplicates
            existing = await self.db.execute(
                select(AnalysisJob.id).where(
                    AnalysisJob.field_id == fid,
                    AnalysisJob.scene_id == scene_id,
                    AnalysisJob.index_type == index_type,
                    AnalysisJob.status.in_(["pending", "running", "complete"]),
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            job = AnalysisJob(
                field_id=fid,
                scene_id=scene_id,
                index_type=index_type,
                status="pending",
                created_by=created_by,
            )
            self.db.add(job)
            jobs.append(job)

        if jobs:
            await self.db.flush()
            for j in jobs:
                await self.db.refresh(j)
            log.info("Queued %d auto-analysis jobs for scene %s", len(jobs), scene_id)

        return jobs

    async def get_pending_jobs(self, limit: int = 100) -> list[AnalysisJob]:
        """Fetch oldest pending jobs for background processing."""
        result = await self.db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.status == "pending")
            .order_by(AnalysisJob.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_scene_match_summary(self, scene_id: str) -> dict:
        """Return a summary of how many fields match and how many jobs exist."""
        matches = await self.match_scene_to_fields(scene_id)

        job_count = await self.db.execute(
            select(func.count()).select_from(AnalysisJob).where(AnalysisJob.scene_id == scene_id)
        )
        total_jobs = job_count.scalar_one()

        complete_count = await self.db.execute(
            select(func.count())
            .select_from(AnalysisJob)
            .where(AnalysisJob.scene_id == scene_id, AnalysisJob.status == "complete")
        )
        completed = complete_count.scalar_one()

        return {
            "scene_id": scene_id,
            "matching_fields": len(matches),
            "total_jobs": total_jobs,
            "completed_jobs": completed,
            "fields": matches,
        }
