"""Highlight working set endpoints — user-scoped geometry selection."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.highlight import HighlightGeometryService, HighlightService

router = APIRouter(prefix="/highlights", tags=["highlights"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class HighlightAddRequest(BaseModel):
    field_ids: list[UUID] = Field(..., min_length=1)


class HighlightRemoveRequest(BaseModel):
    field_ids: list[UUID] = Field(..., min_length=1)


class HighlightSet(BaseModel):
    field_ids: list[str]
    count: int


class GeometryOpRequest(BaseModel):
    geometry: dict | None = None  # GeoJSON geometry for clip/hole


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=HighlightSet, summary="Get highlights")
async def get_highlights(
    current_user: Annotated[User, Depends(get_current_user)],
) -> HighlightSet:
    """Get the current user's highlighted field IDs."""
    svc = HighlightService()
    ids = await svc.list(current_user.id)
    return HighlightSet(field_ids=ids, count=len(ids))


@router.post("", response_model=HighlightSet, summary="Add highlights")
async def add_highlights(
    body: HighlightAddRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HighlightSet:
    """Add field IDs to the highlight set."""
    svc = HighlightService()
    ids = await svc.add(current_user.id, body.field_ids)
    return HighlightSet(field_ids=ids, count=len(ids))


@router.delete("", response_model=HighlightSet, summary="Remove highlights")
async def remove_highlights(
    body: HighlightRemoveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> HighlightSet:
    """Remove field IDs from the highlight set."""
    svc = HighlightService()
    ids = await svc.remove(current_user.id, body.field_ids)
    return HighlightSet(field_ids=ids, count=len(ids))


@router.delete("/all", status_code=204, summary="Clear highlights")
async def clear_highlights(
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Clear the entire highlight set."""
    svc = HighlightService()
    await svc.clear(current_user.id)


@router.post("/merge", summary="Merge highlights")
async def merge_highlights(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Merge (union) all highlighted geometries into one GeoJSON geometry."""
    hl_svc = HighlightService()
    ids = await hl_svc.list(current_user.id)
    if not ids:
        return {"geometry": None}

    geo_svc = HighlightGeometryService(db)
    result = await geo_svc.merge([UUID(fid) for fid in ids])
    return {"geometry": result}


@router.post("/clip", summary="Clip highlights")
async def clip_highlights(
    body: GeometryOpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Clip highlighted geometries by a provided polygon."""
    if body.geometry is None:
        return {"geometry": None}

    hl_svc = HighlightService()
    ids = await hl_svc.list(current_user.id)
    if not ids:
        return {"geometry": None}

    geo_svc = HighlightGeometryService(db)
    result = await geo_svc.clip([UUID(fid) for fid in ids], body.geometry)
    return {"geometry": result}


@router.post("/hole", summary="Hole highlights")
async def hole_highlights(
    body: GeometryOpRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Cut a hole in the highlighted geometries using a provided polygon."""
    if body.geometry is None:
        return {"geometry": None}

    hl_svc = HighlightService()
    ids = await hl_svc.list(current_user.id)
    if not ids:
        return {"geometry": None}

    geo_svc = HighlightGeometryService(db)
    result = await geo_svc.hole([UUID(fid) for fid in ids], body.geometry)
    return {"geometry": result}
