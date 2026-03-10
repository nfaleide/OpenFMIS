"""Region CRUD + membership endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.region import (
    RegionCreate,
    RegionList,
    RegionMemberAdd,
    RegionMemberRemove,
    RegionRead,
    RegionReadWithFields,
    RegionUpdate,
)
from openfmis.services.region import RegionService

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("", response_model=RegionList)
async def list_regions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    group_id: UUID | None = None,
) -> RegionList:
    svc = RegionService(db)
    regions, member_counts, total = await svc.list_regions(
        offset=offset, limit=limit, group_id=group_id
    )
    items = []
    for region, count in zip(regions, member_counts):
        data = RegionRead.model_validate(region).model_dump()
        data["field_count"] = count
        items.append(RegionRead(**data))
    return RegionList(items=items, total=total)


@router.get("/{region_id}", response_model=RegionReadWithFields)
async def get_region(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    svc = RegionService(db)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    field_count = len(field_ids)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = field_count
    data["field_ids"] = field_ids
    return RegionReadWithFields(**data)


@router.post("", response_model=RegionRead, status_code=201)
async def create_region(
    body: RegionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionRead:
    svc = RegionService(db)
    region = await svc.create_region(body, created_by=current_user.id)
    field_count = await svc.get_field_count(region.id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = field_count
    return RegionRead(**data)


@router.patch("/{region_id}", response_model=RegionRead)
async def update_region(
    region_id: UUID,
    body: RegionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionRead:
    svc = RegionService(db)
    region = await svc.update_region(region_id, body)
    field_count = await svc.get_field_count(region.id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = field_count
    return RegionRead(**data)


@router.delete("/{region_id}", status_code=204)
async def delete_region(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = RegionService(db)
    await svc.soft_delete(region_id)


@router.post("/{region_id}/members", response_model=RegionReadWithFields)
async def add_members(
    region_id: UUID,
    body: RegionMemberAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    svc = RegionService(db)
    await svc.add_members(region_id, body.field_ids)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = len(field_ids)
    data["field_ids"] = field_ids
    return RegionReadWithFields(**data)


@router.delete("/{region_id}/members", response_model=RegionReadWithFields)
async def remove_members(
    region_id: UUID,
    body: RegionMemberRemove,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    svc = RegionService(db)
    await svc.remove_members(region_id, body.field_ids)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = len(field_ids)
    data["field_ids"] = field_ids
    return RegionReadWithFields(**data)


@router.get("/{region_id}/fields", response_model=list[UUID])
async def get_region_fields(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[UUID]:
    """Get field IDs belonging to a region."""
    svc = RegionService(db)
    await svc.get_by_id(region_id)  # Validate region exists
    return await svc.get_member_field_ids(region_id)
