"""CLU endpoints — USDA Common Land Unit spatial queries."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.clu import CLUService

router = APIRouter(prefix="/clu", tags=["clu"])


@router.get("/states")
async def list_clu_states(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """Return all states with CLU data loaded."""
    svc = CLUService(db)
    return await svc.get_available_states()


@router.get("/county/{state}/{county_fips}")
async def get_clus_by_county(
    state: str,
    county_fips: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Return paginated CLUs for a state+county FIPS combination.

    Example: GET /api/v1/clu/county/ND/ND001
    """
    svc = CLUService(db)
    items, total = await svc.get_clus_by_county(state, county_fips, offset=offset, limit=limit)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/at-point")
async def get_clus_at_point(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    lon: float = Query(..., description="Longitude (WGS84)"),
    lat: float = Query(..., description="Latitude (WGS84)"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """Return CLU polygons at a given point."""
    svc = CLUService(db)
    return await svc.get_clus_at_point(lon, lat, limit=limit)


@router.post("/intersecting")
async def get_clus_intersecting(
    geometry: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(200, ge=1, le=1000),
) -> list[dict]:
    """Return CLUs intersecting an arbitrary GeoJSON geometry.

    Body: any GeoJSON geometry object (Polygon, MultiPolygon, etc.)
    """
    svc = CLUService(db)
    return await svc.get_clus_intersecting_geometry(geometry, limit=limit)


@router.get("/fields/{field_id}")
async def get_clus_for_field(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Return all CLU polygons intersecting a stored field boundary."""
    svc = CLUService(db)
    return await svc.get_clus_for_field(field_id)
