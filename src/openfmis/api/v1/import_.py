"""Import endpoints — vector file ingestion."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import ValidationError
from openfmis.models.user import User
from openfmis.schemas.import_ import ImportResult
from openfmis.services.import_ import ImportService

router = APIRouter(prefix="/import", tags=["import"])

# 50 MB upload limit
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/vector", response_model=ImportResult, status_code=200)
async def import_vector(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Shapefile (.zip), GeoJSON, KML, or CSV")],
    group_id: Annotated[UUID, Form(description="Group that will own the imported fields")],
    name_field: Annotated[
        str | None,
        Form(description="Attribute name to use as the field name (auto-detected if omitted)"),
    ] = None,
) -> ImportResult:
    """Import vector geometries from a file and create Field records.

    Accepted formats:
    - **Shapefile** — zip archive containing .shp/.dbf/.shx (+ optional .prj)
    - **GeoJSON** — .geojson or .json
    - **KML** — .kml
    - **CSV** — with a `wkt` column or `lat`/`lon` columns

    Returns a summary of created fields, skipped features, and any per-feature errors.
    """
    if file.filename is None:
        raise ValidationError("File must have a filename.")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    svc = ImportService(db)
    return await svc.import_vector(
        file_content=content,
        filename=file.filename,
        group_id=group_id,
        created_by=current_user.id,
        name_field=name_field,
    )
