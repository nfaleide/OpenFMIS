"""PLSS search endpoints — townships and sections."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import NotFoundError
from openfmis.models.user import User
from openfmis.services.plss import PLSSService

router = APIRouter(prefix="/plss", tags=["plss"])


@router.get("/states", summary="List plss states")
async def list_plss_states(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """Return all states with PLSS data loaded."""
    svc = PLSSService(db)
    return await svc.get_available_states()


@router.get("/fips", summary="Get fips for state")
async def get_fips_for_state(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    state: str = Query(..., description="Two-letter state code"),
) -> list[str]:
    """Return distinct FIPS county codes for a state."""
    svc = PLSSService(db)
    return await svc.get_counties_for_state(state)


@router.get("/townships", summary="Search townships")
async def search_townships(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(None, description="Search label or lndkey (e.g. '2S 5E', 'ND06')"),
    state: str | None = Query(None, description="Two-letter state code"),
    fips_c: str | None = Query(None, description="County FIPS code filter"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict]:
    """Search PLSS townships by label, lndkey prefix, state, or FIPS county."""
    svc = PLSSService(db)
    return await svc.search_townships(q=q, state=state, fips_c=fips_c, limit=limit)


@router.get("/townships/{township_id}", summary="Get township")
async def get_township(
    township_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Get a single township by ID."""
    svc = PLSSService(db)
    result = await svc.get_township(township_id)
    if result is None:
        raise NotFoundError("Township not found")
    return result


@router.get("/townships/{township_id}/sections", summary="Get sections for township")
async def get_sections_for_township(
    township_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Return all sections in a township."""
    svc = PLSSService(db)
    twn = await svc.get_township(township_id)
    if twn is None:
        raise NotFoundError("Township not found")
    lndkey = twn["lndkey"] or ""
    return await svc.get_sections_for_township(lndkey)


@router.get("/sections", summary="Search sections")
async def search_sections(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    q: str | None = Query(None, description="Search mtrs, label, or sectionkey"),
    state: str | None = Query(None, description="Two-letter state code"),
    mtrs: str | None = Query(None, description="Meridian-Township-Range-Section string"),
    fips_c: str | None = Query(None, description="County FIPS code"),
    limit: int = Query(50, ge=1, le=200),
) -> list[dict]:
    """Search PLSS sections."""
    svc = PLSSService(db)
    return await svc.search_sections(q=q, state=state, mtrs=mtrs, fips_c=fips_c, limit=limit)


@router.get("/sections/{section_id}", summary="Get section")
async def get_section(
    section_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Get a single section by ID."""
    svc = PLSSService(db)
    result = await svc.get_section(section_id)
    if result is None:
        raise NotFoundError("Section not found")
    return result


@router.get("/at-point", summary="Plss at point")
async def plss_at_point(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    lon: float = Query(..., description="Longitude (WGS84)"),
    lat: float = Query(..., description="Latitude (WGS84)"),
) -> dict:
    """Return the township and sections at a given point."""
    svc = PLSSService(db)
    townships = await svc.find_townships_at_point(lon, lat)
    sections = await svc.find_sections_at_point(lon, lat)
    return {"townships": townships, "sections": sections}
