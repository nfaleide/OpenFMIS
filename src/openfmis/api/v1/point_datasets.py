"""PointDataset CRUD + cleaning log endpoints."""

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
from openfmis.models.point_dataset import PointDataset
from openfmis.models.user import User
from openfmis.schemas.point_dataset import (
    CleaningLogCreate,
    CleaningLogOut,
    PointDatasetCreate,
    PointDatasetOut,
    PointDatasetUpdate,
)
from openfmis.services.point_dataset import PointDatasetService

router = APIRouter(prefix="/point-datasets", tags=["point-datasets"])


@router.get("", response_model=list[PointDatasetOut], summary="List point datasets")
async def list_point_datasets(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
    dataset_type: str | None = None,
    crop_year_id: UUID | None = None,
) -> list[PointDatasetOut]:
    if field_id is not None:
        await verify_field_access(current_user, field_id, db)
    svc = PointDatasetService(db)
    items = await svc.list_datasets(
        field_id=field_id,
        dataset_type=dataset_type,
        crop_year_id=crop_year_id,
    )
    return [PointDatasetOut.model_validate(ds) for ds in items]


@router.get("/{dataset_id}", response_model=PointDatasetOut, summary="Get point dataset")
async def get_point_dataset(
    dataset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PointDatasetOut:
    await verify_entity_group_access(
        current_user, dataset_id, PointDataset, db, label="Point dataset"
    )
    svc = PointDatasetService(db)
    ds = await svc.get_by_id(dataset_id)
    return PointDatasetOut.model_validate(ds)


@router.post("", response_model=PointDatasetOut, status_code=201, summary="Create point dataset")
async def create_point_dataset(
    body: PointDatasetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PointDatasetOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = PointDatasetService(db)
    ds = await svc.create(body)
    return PointDatasetOut.model_validate(ds)


@router.patch("/{dataset_id}", response_model=PointDatasetOut, summary="Update point dataset")
async def update_point_dataset(
    dataset_id: UUID,
    body: PointDatasetUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PointDatasetOut:
    await verify_entity_group_access(
        current_user, dataset_id, PointDataset, db, label="Point dataset"
    )
    svc = PointDatasetService(db)
    ds = await svc.update(dataset_id, body)
    return PointDatasetOut.model_validate(ds)


@router.delete("/{dataset_id}", status_code=204, summary="Delete point dataset")
async def delete_point_dataset(
    dataset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await verify_entity_group_access(
        current_user, dataset_id, PointDataset, db, label="Point dataset"
    )
    svc = PointDatasetService(db)
    await svc.soft_delete(dataset_id)


@router.get(
    "/{dataset_id}/cleaning-log",
    response_model=list[CleaningLogOut],
    summary="Get cleaning log",
)
async def get_cleaning_log(
    dataset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[CleaningLogOut]:
    await verify_entity_group_access(
        current_user, dataset_id, PointDataset, db, label="Point dataset"
    )
    svc = PointDatasetService(db)
    logs = await svc.get_cleaning_log(dataset_id)
    return [CleaningLogOut.model_validate(log) for log in logs]


@router.post(
    "/{dataset_id}/cleaning-log",
    response_model=CleaningLogOut,
    status_code=201,
    summary="Add cleaning step",
)
async def add_cleaning_step(
    dataset_id: UUID,
    body: CleaningLogCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CleaningLogOut:
    await verify_entity_group_access(
        current_user, dataset_id, PointDataset, db, label="Point dataset"
    )
    svc = PointDatasetService(db)
    log = await svc.add_cleaning_step(dataset_id, body)
    return CleaningLogOut.model_validate(log)
