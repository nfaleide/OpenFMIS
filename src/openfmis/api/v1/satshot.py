"""Satshot imagery endpoints — scene discovery, analysis zones, analysis jobs."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.satshot import (
    JobCreate,
    SceneSearchParams,
    ZoneCreate,
    ZoneUpdate,
)
from openfmis.services.analysis import (
    AnalysisService,
    FieldNotFoundError,
    ZoneNotFoundError,
    ZoneService,
)
from openfmis.services.scene_discovery import SceneDiscoveryService

router = APIRouter(prefix="/satshot", tags=["satshot"])


# ── Collections ───────────────────────────────────────────────────────────────


@router.get("/collections", response_model=list[dict])
async def list_collections(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """List available satellite data collections (Sentinel-2, Sentinel-1, Landsat, etc.)."""
    svc = SceneDiscoveryService(db)
    return await svc.get_available_collections()


# ── Scene discovery ────────────────────────────────────────────────────────────


@router.post("/scenes/search", response_model=list[dict])
async def search_scenes(
    params: SceneSearchParams,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Search AWS Sentinel-2 STAC for scenes covering a geometry."""
    svc = SceneDiscoveryService(db)
    try:
        return await svc.search_scenes(
            geometry=params.geometry,
            date_from=params.date_from,
            date_to=params.date_to,
            cloud_cover_max=params.cloud_cover_max,
            limit=params.limit,
            collection=params.collection,
            collections=params.collections,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"STAC error: {exc}")


@router.get("/scenes/cached", response_model=list[dict])
async def list_cached_scenes(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """List scenes cached in the local DB."""
    svc = SceneDiscoveryService(db)
    return await svc.list_cached_scenes(limit=limit, offset=offset)


@router.get("/scenes/{scene_id}", response_model=dict)
async def get_scene(
    scene_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Fetch a scene by ID (from cache or live STAC lookup)."""
    svc = SceneDiscoveryService(db)
    try:
        scene = await svc.get_scene_by_id(scene_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"STAC error: {exc}")
    if scene is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    await db.commit()
    return scene


# ── Analysis zones ─────────────────────────────────────────────────────────────


@router.post("/fields/{field_id}/zones", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_zone(
    field_id: uuid.UUID,
    data: ZoneCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneService(db)
    zone = await svc.create_zone(field_id, data, created_by=current_user.id)
    await db.commit()
    await db.refresh(zone)
    zones = await svc.list_zones(field_id)
    return next(z for z in zones if z["id"] == str(zone.id))


@router.get("/fields/{field_id}/zones", response_model=list[dict])
async def list_zones(
    field_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    svc = ZoneService(db)
    return await svc.list_zones(field_id)


@router.get("/zones/{zone_id}", response_model=dict)
async def get_zone(
    zone_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneService(db)
    zone = await svc.get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    geojson = await svc.get_zone_geojson(zone_id)
    return {
        "id": str(zone.id),
        "field_id": str(zone.field_id),
        "name": zone.name,
        "description": zone.description,
        "geometry_geojson": geojson,
        "created_by": str(zone.created_by) if zone.created_by else None,
        "created_at": zone.created_at.isoformat(),
        "updated_at": zone.updated_at.isoformat(),
    }


@router.patch("/zones/{zone_id}", response_model=dict)
async def update_zone(
    zone_id: uuid.UUID,
    data: ZoneUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneService(db)
    try:
        zone = await svc.update_zone(zone_id, data)
    except ZoneNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    await db.commit()
    geojson = await svc.get_zone_geojson(zone_id)
    return {
        "id": str(zone.id),
        "field_id": str(zone.field_id),
        "name": zone.name,
        "description": zone.description,
        "geometry_geojson": geojson,
        "created_by": str(zone.created_by) if zone.created_by else None,
        "created_at": zone.created_at.isoformat(),
        "updated_at": zone.updated_at.isoformat(),
    }


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_zone(
    zone_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = ZoneService(db)
    try:
        await svc.delete_zone(zone_id)
        await db.commit()
    except ZoneNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")


# ── Analysis jobs ──────────────────────────────────────────────────────────────


@router.post("/jobs", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    data: JobCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Submit an analysis job. Returns immediately; processing runs in the background."""
    svc = AnalysisService(db)
    try:
        job = await svc.submit_job(data, created_by=current_user.id)
        await db.commit()
    except FieldNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
    return _job_dict(job)


@router.get("/jobs", response_model=dict)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: uuid.UUID | None = None,
    job_status: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    svc = AnalysisService(db)
    jobs, total = await svc.list_jobs(
        field_id=field_id, status=job_status, limit=limit, offset=offset
    )
    return {"items": [_job_dict(j) for j in jobs], "total": total, "offset": offset, "limit": limit}


@router.get("/jobs/{job_id}", response_model=dict)
async def get_job(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = AnalysisService(db)
    job = await svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_dict(job)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _job_dict(job) -> dict:
    return {
        "id": str(job.id),
        "field_id": str(job.field_id),
        "zone_id": str(job.zone_id) if job.zone_id else None,
        "scene_id": job.scene_id,
        "index_type": job.index_type,
        "status": job.status,
        "result": job.result,
        "error_message": job.error_message,
        "credits_consumed": job.credits_consumed,
        "created_by": str(job.created_by) if job.created_by else None,
        "created_at": job.created_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
