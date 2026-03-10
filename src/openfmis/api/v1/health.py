"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    """Liveness probe — always returns ok."""
    return {"status": "ok"}


@router.get("/ready")
async def health_ready(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Readiness probe — checks PostGIS connectivity."""
    result = await db.execute(text("SELECT PostGIS_Version()"))
    version = result.scalar_one()
    return {"status": "ok", "postgis": version}
