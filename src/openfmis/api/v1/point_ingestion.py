"""Point ingestion endpoints — preview, upload, validate, structured intake."""

import json
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, verify_field_access
from openfmis.models.user import User
from openfmis.schemas.point_dataset import PointDatasetOut
from openfmis.schemas.point_ingestion import (
    CleaningRuleSpec,
    FilePreviewOut,
    StructuredIntakeOut,
    StructuredIntakeRequest,
    ValidationOut,
    ValidationRequest,
)
from openfmis.services.data_validation import validate_rows
from openfmis.services.point_ingestion import PointIngestionService

router = APIRouter(prefix="/point-ingestion", tags=["point-ingestion"])

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@router.post("/preview", response_model=FilePreviewOut, summary="Preview file")
async def preview_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> FilePreviewOut:
    if not file.filename:
        raise HTTPException(400, "File must have a filename")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large")
    svc = PointIngestionService(db)
    try:
        return await svc.preview_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/upload", response_model=PointDatasetOut, status_code=201, summary="Upload file")
async def upload_file(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    field_id: Annotated[UUID, Form()],
    dataset_type: Annotated[str, Form()],
    label: Annotated[str, Form()],
    value_column: Annotated[str | None, Form()] = None,
    unit: Annotated[str | None, Form()] = None,
    crop_year_id: Annotated[UUID | None, Form()] = None,
    sample_date: Annotated[date | None, Form()] = None,
    lat_column: Annotated[str | None, Form()] = None,
    lon_column: Annotated[str | None, Form()] = None,
    cleaning_rules_json: Annotated[str | None, Form()] = None,
) -> PointDatasetOut:
    if not file.filename:
        raise HTTPException(400, "File must have a filename")
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large")

    await verify_field_access(current_user, field_id, db)

    cleaning_rules = None
    if cleaning_rules_json:
        try:
            raw = json.loads(cleaning_rules_json)
            cleaning_rules = [CleaningRuleSpec(**r) for r in raw]
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(400, f"Invalid cleaning_rules_json: {e}")

    svc = PointIngestionService(db)
    try:
        ds = await svc.upload_file(
            file_content=content,
            filename=file.filename,
            field_id=field_id,
            dataset_type=dataset_type,
            label=label,
            value_column=value_column,
            unit=unit,
            crop_year_id=crop_year_id,
            sample_date=sample_date,
            lat_column=lat_column,
            lon_column=lon_column,
            cleaning_rules=cleaning_rules,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return PointDatasetOut.model_validate(ds)


@router.post(
    "/structured",
    response_model=StructuredIntakeOut,
    status_code=201,
    summary="Structured intake",
)
async def structured_intake(
    body: StructuredIntakeRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> StructuredIntakeOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = PointIngestionService(db)
    ds = await svc.structured_intake(
        field_id=body.field_id,
        dataset_type=body.dataset_type,
        label=body.label,
        features=body.features,
        value_column=body.value_column,
        unit=body.unit,
        crop_year_id=body.crop_year_id,
        sample_date=body.sample_date,
        cleaning_log=body.cleaning_log,
    )
    return StructuredIntakeOut(
        dataset_id=ds.id,
        raw_count=ds.raw_count or 0,
        clean_count=ds.clean_count or 0,
    )


@router.post("/validate", response_model=ValidationOut, summary="Validate data")
async def validate_data(
    body: ValidationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ValidationOut:
    issues = validate_rows(
        dataset_type=body.dataset_type,
        values=body.values,
        unit=body.unit,
        check_coordinates=body.check_coordinates,
        conus_only=body.conus_only,
    )
    return ValidationOut(
        valid=len(issues) == 0,
        total_rows=len(body.values),
        issues=issues,
    )
