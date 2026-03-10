"""Imagery export endpoints — GeoJSON, CSV, KML, Shapefile."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.imagery_export import ImageryExportService

router = APIRouter(prefix="/satshot/export", tags=["satshot-export"])


class ExportRequest(BaseModel):
    job_id: uuid.UUID
    format: str = Field("geojson", pattern="^(geojson|csv|kml|shapefile)$")
    zones: list[dict] | None = None


@router.post("/")
async def export_analysis(
    data: ExportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    svc = ImageryExportService(db)
    try:
        if data.format == "geojson":
            result = await svc.export_geojson(data.job_id, zones=data.zones)
            return result
        elif data.format == "csv":
            csv_text = await svc.export_csv(data.job_id, zones=data.zones)
            return Response(
                content=csv_text,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=export.csv"},
            )
        elif data.format == "kml":
            kml_text = await svc.export_kml(data.job_id, zones=data.zones)
            return Response(
                content=kml_text,
                media_type="application/vnd.google-earth.kml+xml",
                headers={"Content-Disposition": "attachment; filename=export.kml"},
            )
        elif data.format == "shapefile":
            if not data.zones:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Shapefile export requires zones with geometries",
                )
            shp_bytes = await svc.export_shapefile_bytes(data.job_id, data.zones)
            return Response(
                content=shp_bytes,
                media_type="application/zip",
                headers={"Content-Disposition": "attachment; filename=export.zip"},
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
