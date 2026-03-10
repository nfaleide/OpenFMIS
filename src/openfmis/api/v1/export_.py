"""Export endpoints — vector file download."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.export_ import ExportService

router = APIRouter(prefix="/export", tags=["export"])


def _parse_field_ids(field_ids: str | None) -> list[UUID] | None:
    """Parse a comma-separated list of UUIDs, or return None."""
    if not field_ids:
        return None
    return [UUID(fid.strip()) for fid in field_ids.split(",") if fid.strip()]


@router.get("/geojson")
async def export_geojson(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = Query(None, description="Filter to a specific group"),
    field_ids: str | None = Query(None, description="Comma-separated field UUIDs"),
) -> Response:
    """Export fields as a GeoJSON FeatureCollection.

    Specify either `group_id`, `field_ids`, or neither (exports all accessible fields).
    """
    import json

    svc = ExportService(db)
    fc = await svc.export_geojson(
        field_ids=_parse_field_ids(field_ids),
        group_id=group_id,
    )
    return Response(
        content=json.dumps(fc, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="fields.geojson"'},
    )


@router.get("/shapefile")
async def export_shapefile(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = Query(None, description="Filter to a specific group"),
    field_ids: str | None = Query(None, description="Comma-separated field UUIDs"),
) -> Response:
    """Export fields as an ESRI Shapefile (returned as a zip archive)."""
    svc = ExportService(db)
    zip_bytes = await svc.export_shapefile(
        field_ids=_parse_field_ids(field_ids),
        group_id=group_id,
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="fields.zip"'},
    )


@router.get("/kml")
async def export_kml(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = Query(None, description="Filter to a specific group"),
    field_ids: str | None = Query(None, description="Comma-separated field UUIDs"),
) -> Response:
    """Export fields as KML."""
    svc = ExportService(db)
    kml_bytes = await svc.export_kml(
        field_ids=_parse_field_ids(field_ids),
        group_id=group_id,
    )
    return Response(
        content=kml_bytes,
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": 'attachment; filename="fields.kml"'},
    )


@router.get("/csv")
async def export_csv(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = Query(None, description="Filter to a specific group"),
    field_ids: str | None = Query(None, description="Comma-separated field UUIDs"),
) -> Response:
    """Export fields as CSV with a WKT geometry column."""
    svc = ExportService(db)
    csv_text = await svc.export_csv(
        field_ids=_parse_field_ids(field_ids),
        group_id=group_id,
    )
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="fields.csv"'},
    )
