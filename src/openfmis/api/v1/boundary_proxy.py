"""Geodata endpoints for CLU/PLSS boundary data from the shared RDS.

The national CLU/PLSS dataset lives on a shared AWS RDS instance.
These endpoints query that database directly via the geodata engine.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_geodata_db
from openfmis.services.clu import CLUService
from openfmis.services.plss import PLSSService

router = APIRouter(prefix="/boundaries", tags=["boundaries"])

_CACHE_24H = {"Cache-Control": "public, max-age=86400"}


# ── CLU endpoints ────────────────────────────────────────────


@router.get("/clus/bbox", summary="Clus bbox")
async def clus_bbox(
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(1000, ge=1, le=2000),
):
    """Return CLU polygons within a bounding box."""
    svc = CLUService(db)
    clus = await svc.get_clus_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=limit)
    return JSONResponse(content={"clus": clus}, headers=_CACHE_24H)


# ── PLSS endpoints ───────────────────────────────────────────


@router.get("/plss/states", summary="Plss states")
async def plss_states(
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
):
    """Return all states with PLSS data."""
    svc = PLSSService(db)
    return await svc.get_available_states()


@router.get("/plss/counties", summary="Plss counties")
async def plss_counties(
    state: str = Query(...),
    db: Annotated[AsyncSession, Depends(get_geodata_db)] = None,
):
    """Get distinct county FIPS codes for a state's townships."""
    svc = PLSSService(db)
    return await svc.get_counties_for_state(state)


@router.get("/plss/townships/bbox", summary="Plss townships bbox")
async def plss_townships_bbox(
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(200, ge=1, le=500),
):
    """Return PLSS townships within a bounding box."""
    svc = PLSSService(db)
    items = await svc.get_townships_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=limit)
    return JSONResponse(content={"items": items, "total": len(items)}, headers=_CACHE_24H)


@router.get("/plss/townships/search", summary="Plss townships search")
async def plss_townships_search(
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
    state: str | None = Query(None),
    q: str | None = Query(None),
    fips_c: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Search PLSS townships by state/label/county."""
    svc = PLSSService(db)
    items = await svc.search_townships(q=q, state=state, fips_c=fips_c, limit=limit)
    return JSONResponse(content={"items": items, "total": len(items)}, headers=_CACHE_24H)


@router.get("/plss/townships/{township_id}", summary="Plss township detail")
async def plss_township_detail(
    township_id: int,
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
):
    """Get a single township by ID with geometry."""
    svc = PLSSService(db)
    result = await svc.get_township(township_id)
    if result is None:
        return JSONResponse(content={"detail": "Not found"}, status_code=404)
    return result


@router.get("/plss/townships/{township_id}/sections", summary="Plss township sections")
async def plss_township_sections(
    township_id: int,
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
):
    """Return all sections in a township."""
    svc = PLSSService(db)
    twn = await svc.get_township(township_id)
    if twn is None:
        return JSONResponse(content={"detail": "Not found"}, status_code=404)
    lndkey = twn.get("lndkey", "")
    sections = await svc.get_sections_for_township(lndkey)
    return sections


@router.get("/plss/sections/bbox", summary="Plss sections bbox")
async def plss_sections_bbox(
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
    min_lon: float = Query(...),
    min_lat: float = Query(...),
    max_lon: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(2000, ge=1, le=5000),
):
    """Return PLSS sections within a bounding box."""
    svc = PLSSService(db)
    items = await svc.get_sections_by_bbox(min_lon, min_lat, max_lon, max_lat, limit=limit)
    return JSONResponse(content={"items": items, "total": len(items)}, headers=_CACHE_24H)


@router.get("/plss/sections/{section_id}", summary="Plss section detail")
async def plss_section_detail(
    section_id: int,
    db: Annotated[AsyncSession, Depends(get_geodata_db)],
):
    """Get a single section by ID with geometry."""
    svc = PLSSService(db)
    result = await svc.get_section(section_id)
    if result is None:
        return JSONResponse(content={"detail": "Not found"}, status_code=404)
    return result
