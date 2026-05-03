"""Export endpoints — vector file download + shareable export links."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import NotFoundError
from openfmis.models.user import User
from openfmis.services.export_ import ExportService

router = APIRouter(prefix="/export", tags=["export"])


def _parse_field_ids(field_ids: str | None) -> list[UUID] | None:
    """Parse a comma-separated list of UUIDs, or return None."""
    if not field_ids:
        return None
    return [UUID(fid.strip()) for fid in field_ids.split(",") if fid.strip()]


@router.get("/geojson", summary="Export geojson")
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


@router.get("/shapefile", summary="Export shapefile")
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


@router.get("/kml", summary="Export kml")
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


@router.get("/csv", summary="Export csv")
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


# ── Export link schemas ──────────────────────────────────────────────────────


class ExportLinkCreate(BaseModel):
    format: str = Field(..., pattern=r"^(geojson|shapefile|kml|csv)$")
    field_ids: list[UUID] | None = None
    group_id: UUID | None = None
    expires_in_hours: int = Field(24, ge=1, le=720)
    max_downloads: int | None = Field(None, ge=1)


class ExportLinkRead(BaseModel):
    id: UUID
    hash: str
    format: str
    filters: dict
    expires_at: datetime
    download_count: int
    max_downloads: int | None
    filename: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Export link endpoints ────────────────────────────────────────────────────


@router.post("/links", response_model=ExportLinkRead, status_code=201, summary="Create export link")
async def create_export_link(
    body: ExportLinkCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ExportLinkRead:
    """Create a shareable download link for an export."""
    svc = ExportService(db)
    link = await svc.create_export_link(
        format=body.format,
        created_by=current_user.id,
        field_ids=body.field_ids,
        group_id=body.group_id,
        expires_in_hours=body.expires_in_hours,
        max_downloads=body.max_downloads,
    )
    return ExportLinkRead.model_validate(link)


@router.get("/links/{link_hash}", summary="Download export link")
async def download_export_link(
    link_hash: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Download an export via a shareable link (no authentication required).

    The link must be valid, not expired, and within its download limit.
    """
    svc = ExportService(db)
    try:
        content, content_type, filename = await svc.consume_export_link(link_hash)
    except NotFoundError as e:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content

    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
