"""Auto-analysis endpoints — scene matching and batch job queuing."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.auto_analysis import AutoAnalysisService

router = APIRouter(prefix="/satshot/auto-analysis", tags=["satshot-auto-analysis"])


class QueueJobsRequest(BaseModel):
    scene_id: str
    index_type: str = "ndvi"
    field_ids: list[uuid.UUID] | None = None


@router.get("/match/{scene_id}", response_model=dict)
async def match_scene(
    scene_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Find all fields that intersect a scene's footprint."""
    svc = AutoAnalysisService(db)
    return await svc.get_scene_match_summary(scene_id)


@router.post("/queue", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def queue_jobs(
    data: QueueJobsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Queue analysis jobs for all matching fields (or specified field_ids)."""
    svc = AutoAnalysisService(db)
    jobs = await svc.queue_jobs_for_scene(
        scene_id=data.scene_id,
        index_type=data.index_type,
        created_by=current_user.id,
        field_ids=data.field_ids,
    )
    await db.commit()
    return {
        "queued": len(jobs),
        "job_ids": [str(j.id) for j in jobs],
    }


@router.get("/pending", response_model=dict)
async def list_pending(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    svc = AutoAnalysisService(db)
    jobs = await svc.get_pending_jobs(limit=limit)
    return {
        "count": len(jobs),
        "jobs": [
            {
                "id": str(j.id),
                "field_id": str(j.field_id),
                "scene_id": j.scene_id,
                "index_type": j.index_type,
            }
            for j in jobs
        ],
    }
