"""Region CRUD + membership endpoints with ACL enforcement."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.schemas.region import (
    AccessibleSet,
    RegionAccessibility,
    RegionCreate,
    RegionList,
    RegionMemberAdd,
    RegionMemberRemove,
    RegionRead,
    RegionReadWithFields,
    RegionUpdate,
)
from openfmis.services.acl import ACLService
from openfmis.services.region import RegionService

router = APIRouter(prefix="/regions", tags=["regions"])


async def _check_region_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: UUID | None = None,
) -> None:
    """Check a regions.* permission, raising 403 if denied."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, permission, "regions", resource_id)
    if not allowed:
        raise AuthorizationError(f"Permission '{permission}' denied on 'regions'")


@router.get("", response_model=RegionList, summary="List regions")
async def list_regions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    group_id: UUID | None = None,
) -> RegionList:
    acl = ACLService(db)
    if not current_user.is_superuser:
        allowed = await acl.check_permission(current_user, "regions.read", "regions")
        if not allowed:
            return RegionList(items=[], total=0)
        if group_id is None:
            group_id = current_user.group_id

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


@router.get("/accessible", response_model=AccessibleSet, summary="Get accessible set")
async def get_accessible_set(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AccessibleSet:
    """Return the full accessible set: regions + fields the user can see."""
    svc = RegionService(db)
    return await svc.get_accessible_set(current_user)


@router.get("/mine", response_model=RegionList, summary="List my regions")
async def list_my_regions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> RegionList:
    """List regions created by the current user."""
    svc = RegionService(db)
    regions, member_counts, total = await svc.list_my_regions(
        current_user, offset=offset, limit=limit
    )
    items = []
    for region, count in zip(regions, member_counts):
        data = RegionRead.model_validate(region).model_dump()
        data["field_count"] = count
        items.append(RegionRead(**data))
    return RegionList(items=items, total=total)


@router.get("/visible", response_model=RegionList, summary="List visible regions")
async def list_visible_regions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> RegionList:
    """List all regions visible to the current user via ACL."""
    svc = RegionService(db)
    regions, member_counts, total = await svc.list_visible_regions(
        current_user, offset=offset, limit=limit
    )
    items = []
    for region, count in zip(regions, member_counts):
        data = RegionRead.model_validate(region).model_dump()
        data["field_count"] = count
        items.append(RegionRead(**data))
    return RegionList(items=items, total=total)


@router.get("/{region_id}", response_model=RegionReadWithFields, summary="Get region")
async def get_region(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    await _check_region_permission(db, current_user, "regions.read", region_id)
    svc = RegionService(db)
    acl = ACLService(db)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    total_area = await svc.get_total_area_acres(region_id)

    # Build accessibility info for the requesting user
    can_modify = await acl.check_permission(current_user, "regions.modify", "regions", region_id)
    can_delete = await acl.check_permission(current_user, "regions.delete", "regions", region_id)
    accessibility = RegionAccessibility(can_read=True, can_modify=can_modify, can_delete=can_delete)

    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = len(field_ids)
    data["field_ids"] = field_ids
    data["total_area_acres"] = total_area
    data["accessibility"] = accessibility
    return RegionReadWithFields(**data)


@router.post("", response_model=RegionRead, status_code=201, summary="Create region")
async def create_region(
    body: RegionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionRead:
    await _check_region_permission(db, current_user, "regions.create")
    svc = RegionService(db)
    region = await svc.create_region(body, created_by=current_user.id)
    field_count = await svc.get_field_count(region.id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = field_count
    return RegionRead(**data)


@router.patch("/{region_id}", response_model=RegionRead, summary="Update region")
async def update_region(
    region_id: UUID,
    body: RegionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionRead:
    await _check_region_permission(db, current_user, "regions.modify", region_id)
    svc = RegionService(db)
    region = await svc.update_region(region_id, body)
    field_count = await svc.get_field_count(region.id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = field_count
    return RegionRead(**data)


@router.delete("/{region_id}", status_code=204, summary="Delete region")
async def delete_region(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _check_region_permission(db, current_user, "regions.delete", region_id)
    svc = RegionService(db)
    await svc.soft_delete(region_id)


@router.post("/{region_id}/members", response_model=RegionReadWithFields, summary="Add members")
async def add_members(
    region_id: UUID,
    body: RegionMemberAdd,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    await _check_region_permission(db, current_user, "regions.modify", region_id)
    # Also verify caller has fields.read on each field being added
    acl = ACLService(db)
    for fid in body.field_ids:
        allowed = await acl.check_permission(current_user, "fields.read", "fields", fid)
        if not allowed:
            raise AuthorizationError(f"Permission 'fields.read' denied on field '{fid}'")
    svc = RegionService(db)
    await svc.add_members(region_id, body.field_ids)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = len(field_ids)
    data["field_ids"] = field_ids
    return RegionReadWithFields(**data)


@router.delete(
    "/{region_id}/members",
    response_model=RegionReadWithFields,
    summary="Remove members",
)
async def remove_members(
    region_id: UUID,
    body: RegionMemberRemove,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> RegionReadWithFields:
    await _check_region_permission(db, current_user, "regions.modify", region_id)
    svc = RegionService(db)
    await svc.remove_members(region_id, body.field_ids)
    region = await svc.get_by_id(region_id)
    field_ids = await svc.get_member_field_ids(region_id)
    data = RegionRead.model_validate(region).model_dump()
    data["field_count"] = len(field_ids)
    data["field_ids"] = field_ids
    return RegionReadWithFields(**data)


@router.get("/{region_id}/fields", response_model=list[UUID], summary="Get region fields")
async def get_region_fields(
    region_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[UUID]:
    """Get field IDs belonging to a region."""
    await _check_region_permission(db, current_user, "regions.read", region_id)
    svc = RegionService(db)
    await svc.get_by_id(region_id)  # Validate region exists
    return await svc.get_member_field_ids(region_id)
