"""CoreDataset CRUD endpoints — plugin-attached datasets."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.plugin_sdk.datasets import (
    attach_dataset,
    delete_dataset,
    get_dataset,
    list_datasets_for_field,
)
from openfmis.services.acl import ACLService

router = APIRouter(prefix="/datasets", tags=["datasets"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class CoreDatasetCreate(BaseModel):
    plugin_slug: str = Field(..., min_length=1, max_length=100)
    dataset_type: str = Field(..., min_length=1, max_length=100)
    field_id: UUID | None = None
    metadata: dict = Field(default_factory=dict)
    storage_url: str | None = None


class CoreDatasetRead(BaseModel):
    id: UUID
    plugin_slug: str
    dataset_type: str
    field_id: UUID | None
    metadata: dict = Field(validation_alias="extra_metadata")
    storage_url: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class CoreDatasetList(BaseModel):
    items: list[CoreDatasetRead]
    total: int


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _check_perm(db: AsyncSession, user: User, perm: str) -> None:
    if user.is_superuser:
        return
    acl = ACLService(db)
    if not await acl.check_permission(user, perm, "fielddata"):
        raise AuthorizationError(f"Permission '{perm}' denied on 'fielddata'")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", response_model=CoreDatasetRead, status_code=201, summary="Create dataset")
async def create_dataset(
    body: CoreDatasetCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CoreDatasetRead:
    await _check_perm(db, current_user, "fielddata.append")
    ds = await attach_dataset(
        db,
        plugin_slug=body.plugin_slug,
        dataset_type=body.dataset_type,
        field_id=body.field_id,
        metadata=body.metadata,
        storage_url=body.storage_url,
        created_by=current_user.id,
    )
    return CoreDatasetRead.model_validate(ds)


@router.get("", response_model=CoreDatasetList, summary="List datasets")
async def list_datasets(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID = Query(...),
    plugin_slug: str | None = None,
    dataset_type: str | None = None,
) -> CoreDatasetList:
    await _check_perm(db, current_user, "fielddata.read")
    items = await list_datasets_for_field(
        db, field_id, plugin_slug=plugin_slug, dataset_type=dataset_type
    )
    return CoreDatasetList(
        items=[CoreDatasetRead.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("/{dataset_id}", response_model=CoreDatasetRead, summary="Get dataset detail")
async def get_dataset_detail(
    dataset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CoreDatasetRead:
    await _check_perm(db, current_user, "fielddata.read")
    ds = await get_dataset(db, dataset_id)
    return CoreDatasetRead.model_validate(ds)


@router.delete("/{dataset_id}", status_code=204, summary="Remove dataset")
async def remove_dataset(
    dataset_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _check_perm(db, current_user, "fielddata.modify")
    await delete_dataset(db, dataset_id)
