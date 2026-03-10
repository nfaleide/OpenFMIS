"""Batch analysis endpoints — multi-field and area-based analysis."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.batch_analysis import BatchAnalysisService

router = APIRouter(prefix="/satshot/batch", tags=["satshot-batch"])


class BatchByFieldsRequest(BaseModel):
    field_ids: list[uuid.UUID] = Field(..., min_length=1)
    scene_id: str
    index_type: str
    name: str | None = None


class BatchByAreaRequest(BaseModel):
    geometry: dict[str, Any] = Field(..., description="GeoJSON geometry covering the area")
    scene_id: str
    index_type: str
    name: str | None = None


class BatchByPLSSRequest(BaseModel):
    plss_id: uuid.UUID
    plss_type: str = Field(..., pattern="^(township|section)$")
    scene_id: str
    index_type: str


@router.post("/fields", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def create_batch_by_fields(
    data: BatchByFieldsRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = BatchAnalysisService(db)
    batch = await svc.create_batch(
        data.field_ids,
        data.scene_id,
        data.index_type,
        created_by=current_user.id,
        name=data.name,
    )
    await db.commit()
    return {"batch_id": str(batch.id), "name": batch.name, "job_count": len(batch.job_ids or [])}


@router.post("/area", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def create_batch_by_area(
    data: BatchByAreaRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Find all fields within a geometry and run batch analysis."""
    svc = BatchAnalysisService(db)
    try:
        batch = await svc.create_batch_by_area(
            data.geometry,
            data.scene_id,
            data.index_type,
            created_by=current_user.id,
            name=data.name,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"batch_id": str(batch.id), "name": batch.name, "job_count": len(batch.job_ids or [])}


@router.post("/plss", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def create_batch_by_plss(
    data: BatchByPLSSRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Find all fields within a PLSS township/section and run batch analysis."""
    svc = BatchAnalysisService(db)
    try:
        batch = await svc.create_batch_by_plss(
            data.plss_id,
            data.plss_type,
            data.scene_id,
            data.index_type,
            created_by=current_user.id,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"batch_id": str(batch.id), "name": batch.name, "job_count": len(batch.job_ids or [])}


@router.get("/{batch_id}", response_model=dict)
async def get_batch_status(
    batch_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = BatchAnalysisService(db)
    try:
        return await svc.get_batch_status(batch_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/", response_model=list[dict])
async def list_batches(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    svc = BatchAnalysisService(db)
    batches = await svc.list_batches(created_by=current_user.id, limit=limit, offset=offset)
    return [
        {
            "id": str(b.id),
            "name": b.name,
            "scene_id": b.scene_id,
            "index_type": b.index_type,
            "status": b.status,
            "field_count": len(b.field_ids) if b.field_ids else 0,
            "summary": b.summary,
            "created_at": b.created_at.isoformat(),
        }
        for b in batches
    ]
