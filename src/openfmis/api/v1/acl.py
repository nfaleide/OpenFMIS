"""ACL endpoints — manage and check permissions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.privilege import (
    EffectivePermissions,
    GroupPrivilegeRead,
    PermissionCheck,
    PrivilegeGrant,
    UserPrivilegeRead,
)
from openfmis.services.acl import ACLService
from openfmis.services.user import UserService

router = APIRouter(prefix="/acl", tags=["acl"])


# ── Check permissions ─────────────────────────────────────────


@router.get("/check")
async def check_permission(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    permission: str = Query(...),
    resource_type: str = Query(...),
    resource_id: UUID | None = None,
    user_id: UUID | None = None,
) -> PermissionCheck:
    """Check if a user has a specific permission.

    If user_id is omitted, checks the current user.
    """
    acl = ACLService(db)

    if user_id is not None and user_id != current_user.id:
        user_svc = UserService(db)
        target_user = await user_svc.get_by_id(user_id)
    else:
        target_user = current_user

    granted = await acl.check_permission(target_user, permission, resource_type, resource_id)
    source = None
    if granted:
        source = "superuser" if target_user.is_superuser else "acl"
    return PermissionCheck(permission=permission, granted=granted, source=source)


@router.get("/effective")
async def get_effective_permissions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    resource_type: str = Query(...),
    resource_id: UUID | None = None,
    user_id: UUID | None = None,
) -> EffectivePermissions:
    """Get all effective permissions for a user on a resource type."""
    acl = ACLService(db)

    if user_id is not None and user_id != current_user.id:
        user_svc = UserService(db)
        target_user = await user_svc.get_by_id(user_id)
    else:
        target_user = current_user

    perms = await acl.get_effective_permissions(target_user, resource_type, resource_id)
    return EffectivePermissions(
        user_id=target_user.id,
        resource_type=resource_type,
        resource_id=resource_id,
        permissions=perms,
    )


# ── User privileges ───────────────────────────────────────────


@router.get("/users/{user_id}/privileges", response_model=list[UserPrivilegeRead])
async def list_user_privileges(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[UserPrivilegeRead]:
    acl = ACLService(db)
    privs = await acl.list_user_privileges(user_id)
    return [UserPrivilegeRead.model_validate(p) for p in privs]


@router.post("/users/{user_id}/privileges", response_model=UserPrivilegeRead, status_code=201)
async def grant_user_privilege(
    user_id: UUID,
    body: PrivilegeGrant,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserPrivilegeRead:
    acl = ACLService(db)
    priv = await acl.grant_user_privilege(user_id, body)
    return UserPrivilegeRead.model_validate(priv)


@router.delete("/users/{user_id}/privileges", status_code=204)
async def revoke_user_privilege(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    resource_type: str = Query(...),
    resource_id: UUID | None = None,
) -> None:
    acl = ACLService(db)
    await acl.revoke_user_privilege(user_id, resource_type, resource_id)


# ── Group privileges ──────────────────────────────────────────


@router.get("/groups/{group_id}/privileges", response_model=list[GroupPrivilegeRead])
async def list_group_privileges(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[GroupPrivilegeRead]:
    acl = ACLService(db)
    privs = await acl.list_group_privileges(group_id)
    return [GroupPrivilegeRead.model_validate(p) for p in privs]


@router.post("/groups/{group_id}/privileges", response_model=GroupPrivilegeRead, status_code=201)
async def grant_group_privilege(
    group_id: UUID,
    body: PrivilegeGrant,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupPrivilegeRead:
    acl = ACLService(db)
    priv = await acl.grant_group_privilege(group_id, body)
    return GroupPrivilegeRead.model_validate(priv)


@router.delete("/groups/{group_id}/privileges", status_code=204)
async def revoke_group_privilege(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    resource_type: str = Query(...),
    resource_id: UUID | None = None,
) -> None:
    acl = ACLService(db)
    await acl.revoke_group_privilege(group_id, resource_type, resource_id)
