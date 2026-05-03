"""Field CRUD endpoints with geometry, versioning, and ACL enforcement."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.schemas.field import (
    BatchRenameRequest,
    BatchRenameResult,
    FieldCreate,
    FieldList,
    FieldRead,
    FieldReadWithGeometry,
    FieldUpdate,
    FieldVersionHistory,
)
from openfmis.services.acl import ACLService
from openfmis.services.field import FieldService

router = APIRouter(prefix="/fields", tags=["fields"])


async def _check_field_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: UUID | None = None,
) -> None:
    """Check a fields.* permission, raising 403 if denied."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, permission, "fields", resource_id)
    if not allowed:
        raise AuthorizationError(f"Permission '{permission}' denied on 'fields'")


@router.get("", response_model=FieldList, summary="List fields")
async def list_fields(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    group_id: UUID | None = None,
    region_id: UUID | None = None,
    current_only: bool = True,
) -> FieldList:
    # Check wildcard fields.read — if DENY, return empty list
    acl = ACLService(db)
    if not current_user.is_superuser:
        allowed = await acl.check_permission(current_user, "fields.read", "fields")
        if not allowed:
            return FieldList(items=[], total=0)
        # Non-superusers scoped to their own group unless a specific group_id is passed
        if group_id is None:
            group_id = current_user.group_id

    svc = FieldService(db)
    fields, total = await svc.list_fields(
        offset=offset,
        limit=limit,
        group_id=group_id,
        region_id=region_id,
        current_only=current_only,
    )
    return FieldList(items=[FieldRead.model_validate(f) for f in fields], total=total)


@router.get("/{field_id}", response_model=FieldReadWithGeometry, summary="Get field")
async def get_field(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldReadWithGeometry:
    await _check_field_permission(db, current_user, "fields.read", field_id)
    svc = FieldService(db)
    field = await svc.get_by_id(field_id)
    geojson = await svc.get_geometry_geojson(field_id)
    data = FieldRead.model_validate(field).model_dump()
    data["geometry_geojson"] = geojson
    return FieldReadWithGeometry(**data)


@router.get(
    "/{field_id}/versions",
    response_model=FieldVersionHistory,
    summary="Get field versions",
)
async def get_field_versions(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldVersionHistory:
    await _check_field_permission(db, current_user, "fields.read", field_id)
    svc = FieldService(db)
    versions = await svc.get_version_history(field_id)
    return FieldVersionHistory(versions=[FieldRead.model_validate(v) for v in versions])


@router.post("", response_model=FieldRead, status_code=201, summary="Create field")
async def create_field(
    body: FieldCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    await _check_field_permission(db, current_user, "fields.create")
    svc = FieldService(db)
    field = await svc.create_field(body, created_by=current_user.id)
    return FieldRead.model_validate(field)


@router.patch("/{field_id}", response_model=FieldRead, summary="Update field")
async def update_field(
    field_id: UUID,
    body: FieldUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    await _check_field_permission(db, current_user, "fields.modify", field_id)
    svc = FieldService(db)
    field = await svc.update_field(field_id, body)
    return FieldRead.model_validate(field)


@router.put("/{field_id}/geometry", response_model=FieldRead, summary="Update field geometry")
async def update_field_geometry(
    field_id: UUID,
    geometry_geojson: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    """Update field geometry — creates a new version."""
    await _check_field_permission(db, current_user, "fields.modify", field_id)
    svc = FieldService(db)
    new_field = await svc.update_geometry(field_id, geometry_geojson)
    return FieldRead.model_validate(new_field)


@router.post("/batch-rename", response_model=BatchRenameResult, summary="Batch rename fields")
async def batch_rename_fields(
    body: BatchRenameRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BatchRenameResult:
    """Rename multiple fields at once, checking per-field ACL."""
    acl = ACLService(db)
    svc = FieldService(db)

    allowed_renames: list[tuple[UUID, str]] = []
    denied: list[UUID] = []
    not_found: list[UUID] = []

    for item in body.renames:
        has_perm = await acl.check_permission(
            current_user, "fields.modify", "fields", item.field_id
        )
        if not has_perm:
            denied.append(item.field_id)
        else:
            allowed_renames.append((item.field_id, item.name))

    renamed = await svc.batch_rename(allowed_renames)

    # Any field_id in allowed_renames but not in renamed was not found
    renamed_set = set(renamed)
    for fid, _ in allowed_renames:
        if fid not in renamed_set:
            not_found.append(fid)

    return BatchRenameResult(renamed=renamed, denied=denied, not_found=not_found)


@router.delete("/{field_id}", status_code=204, summary="Delete field")
async def delete_field(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _check_field_permission(db, current_user, "fields.delete", field_id)
    svc = FieldService(db)
    await svc.soft_delete(field_id)
