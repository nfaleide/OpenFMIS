"""CropYear CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import (
    get_current_user,
    verify_entity_group_access,
    verify_field_access,
)
from openfmis.models.crop_year import CropYear
from openfmis.models.user import User
from openfmis.schemas.crop_year import CropYearCreate, CropYearOut, CropYearUpdate
from openfmis.services.crop_year import CropYearService

router = APIRouter(prefix="/crop-years", tags=["crop-years"])


@router.get("", response_model=list[CropYearOut], summary="List crop years")
async def list_crop_years(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
) -> list[CropYearOut]:
    svc = CropYearService(db)
    if field_id is None:
        return []
    await verify_field_access(current_user, field_id, db)
    items = await svc.list_by_field(field_id)
    return [CropYearOut.model_validate(i) for i in items]


@router.get("/{crop_year_id}", response_model=CropYearOut, summary="Get crop year")
async def get_crop_year(
    crop_year_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CropYearOut:
    await verify_entity_group_access(current_user, crop_year_id, CropYear, db, label="Crop year")
    svc = CropYearService(db)
    cy = await svc.get_by_id(crop_year_id)
    return CropYearOut.model_validate(cy)


@router.post("", response_model=CropYearOut, status_code=201, summary="Create crop year")
async def create_crop_year(
    body: CropYearCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CropYearOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = CropYearService(db)
    cy = await svc.create(body)
    return CropYearOut.model_validate(cy)


@router.patch("/{crop_year_id}", response_model=CropYearOut, summary="Update crop year")
async def update_crop_year(
    crop_year_id: UUID,
    body: CropYearUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CropYearOut:
    await verify_entity_group_access(current_user, crop_year_id, CropYear, db, label="Crop year")
    svc = CropYearService(db)
    cy = await svc.update(crop_year_id, body)
    return CropYearOut.model_validate(cy)


@router.delete("/{crop_year_id}", status_code=204, summary="Delete crop year")
async def delete_crop_year(
    crop_year_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await verify_entity_group_access(current_user, crop_year_id, CropYear, db, label="Crop year")
    svc = CropYearService(db)
    await svc.soft_delete(crop_year_id)
