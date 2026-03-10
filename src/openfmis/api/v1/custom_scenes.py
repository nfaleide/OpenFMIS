"""Custom imagery upload endpoints."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.custom_imagery import CustomImageryService

router = APIRouter(prefix="/satshot/scenes/custom", tags=["satshot-custom-imagery"])

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_scene(
    file: UploadFile = File(...),
    name: str = Form(None),
    description: str = Form(None),
    band_names: str = Form(None),  # comma-separated
    acquired_at: str = Form(None),  # ISO datetime
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a GeoTIFF for analysis. Processing happens in the background."""
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    parsed_bands = band_names.split(",") if band_names else None
    parsed_date = datetime.fromisoformat(acquired_at) if acquired_at else None

    group_id = getattr(current_user, "group_id", None)
    if group_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a group"
        )

    svc = CustomImageryService(db)
    scene = await svc.upload(
        file_bytes=content,
        filename=file.filename or "upload.tif",
        group_id=group_id,
        uploaded_by=current_user.id,
        name=name,
        description=description,
        band_names=parsed_bands,
        acquired_at=parsed_date,
    )
    await db.commit()

    return {
        "id": str(scene.id),
        "name": scene.name,
        "status": scene.status,
        "file_size_bytes": scene.file_size_bytes,
    }


@router.get("/", response_model=list[dict])
async def list_custom_scenes(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    group_id = getattr(current_user, "group_id", None)
    if group_id is None:
        return []

    svc = CustomImageryService(db)
    scenes = await svc.list_scenes(group_id, limit=limit, offset=offset)
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "status": s.status,
            "band_count": s.band_count,
            "band_names": s.band_names,
            "crs": s.crs,
            "bounds": s.bounds,
            "acquired_at": s.acquired_at.isoformat() if s.acquired_at else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in scenes
    ]


@router.get("/{scene_id}", response_model=dict)
async def get_custom_scene(
    scene_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = CustomImageryService(db)
    scene = await svc.get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Custom scene not found")
    return {
        "id": str(scene.id),
        "name": scene.name,
        "description": scene.description,
        "status": scene.status,
        "band_count": scene.band_count,
        "band_names": scene.band_names,
        "band_metadata": scene.band_metadata,
        "crs": scene.crs,
        "bounds": scene.bounds,
        "pixel_resolution_m": scene.pixel_resolution_m,
        "file_size_bytes": scene.file_size_bytes,
        "acquired_at": scene.acquired_at.isoformat() if scene.acquired_at else None,
        "scene_record_id": str(scene.scene_record_id) if scene.scene_record_id else None,
        "created_at": scene.created_at.isoformat(),
    }


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_scene(
    scene_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = CustomImageryService(db)
    try:
        await svc.delete_scene(scene_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
