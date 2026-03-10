"""Zone editing endpoints — merge, paint, dissolve, split, buffer."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.zone_editing import (
    ZoneBufferRequest,
    ZoneDissolveRequest,
    ZoneMergeRequest,
    ZonePaintRequest,
    ZoneSplitRequest,
)
from openfmis.services.zone_editing import ZoneEditingService, ZoneNotFoundError

router = APIRouter(prefix="/satshot/zones", tags=["satshot-zone-editing"])


@router.post("/merge", response_model=dict, status_code=status.HTTP_201_CREATED)
async def merge_zones(
    data: ZoneMergeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneEditingService(db)
    try:
        merged = await svc.merge_zones(data.zone_ids, data.merged_name, created_by=current_user.id)
        await db.commit()
    except ZoneNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"id": str(merged.id), "name": merged.name, "field_id": str(merged.field_id)}


@router.post("/{zone_id}/paint", response_model=dict)
async def paint_zone(
    zone_id: uuid.UUID,
    data: ZonePaintRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneEditingService(db)
    try:
        zone = await svc.paint_zone(zone_id, data.geometry, created_by=current_user.id)
        await db.commit()
    except ZoneNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return {"id": str(zone.id), "name": zone.name}


@router.post("/dissolve", response_model=list[dict])
async def dissolve_zones(
    data: ZoneDissolveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    svc = ZoneEditingService(db)
    try:
        zones = await svc.dissolve_zones(data.zone_ids)
        await db.commit()
    except ZoneNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return [{"id": str(z.id), "name": z.name} for z in zones]


@router.post("/{zone_id}/split", response_model=list[dict], status_code=status.HTTP_201_CREATED)
async def split_zone(
    zone_id: uuid.UUID,
    data: ZoneSplitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    svc = ZoneEditingService(db)
    try:
        zones = await svc.split_zone(zone_id, data.split_line, created_by=current_user.id)
        await db.commit()
    except ZoneNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return [{"id": str(z.id), "name": z.name} for z in zones]


@router.post("/{zone_id}/buffer", response_model=dict)
async def buffer_zone(
    zone_id: uuid.UUID,
    data: ZoneBufferRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = ZoneEditingService(db)
    try:
        zone = await svc.buffer_zone(zone_id, data.distance_meters)
        await db.commit()
    except ZoneNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return {"id": str(zone.id), "name": zone.name}
