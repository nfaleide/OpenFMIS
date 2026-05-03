"""Group CRUD endpoints + hierarchy queries."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.schemas.group import (
    GroupAncestry,
    GroupCreate,
    GroupList,
    GroupRead,
    GroupUpdate,
)
from openfmis.services.acl import ACLService
from openfmis.services.group import GroupService

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=GroupList, summary="List groups")
async def list_groups(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    parent_id: UUID | None = None,
    root_only: bool = False,
) -> GroupList:
    svc = GroupService(db)
    groups, total = await svc.list_groups(
        offset=offset, limit=limit, parent_id=parent_id, root_only=root_only
    )
    return GroupList(items=[GroupRead.model_validate(g) for g in groups], total=total)


@router.get("/tree", summary="Get group tree")
async def get_group_tree(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    root_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Return nested group tree. If root_id given, tree from that node."""
    svc = GroupService(db)
    return await svc.get_tree(root_id)


@router.get("/{group_id}", response_model=GroupRead, summary="Get group")
async def get_group(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupRead:
    svc = GroupService(db)
    group = await svc.get_by_id(group_id)
    return GroupRead.model_validate(group)


@router.get("/{group_id}/ancestors", response_model=GroupAncestry, summary="Get ancestors")
async def get_ancestors(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupAncestry:
    svc = GroupService(db)
    ancestors = await svc.get_ancestors(group_id)
    return GroupAncestry(ancestors=[GroupRead.model_validate(g) for g in ancestors])


@router.get("/{group_id}/descendants", response_model=list[GroupRead], summary="Get descendants")
async def get_descendants(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[GroupRead]:
    svc = GroupService(db)
    descendants = await svc.get_descendants(group_id)
    return [GroupRead.model_validate(g) for g in descendants]


@router.post("", response_model=GroupRead, status_code=201, summary="Create group")
async def create_group(
    body: GroupCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupRead:
    await _require_group_admin(db, current_user)
    svc = GroupService(db)
    group = await svc.create_group(body)
    return GroupRead.model_validate(group)


@router.patch("/{group_id}", response_model=GroupRead, summary="Update group")
async def update_group(
    group_id: UUID,
    body: GroupUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GroupRead:
    await _require_group_admin(db, current_user)
    svc = GroupService(db)
    group = await svc.update_group(group_id, body)
    return GroupRead.model_validate(group)


@router.delete("/{group_id}", status_code=204, summary="Delete group")
async def delete_group(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _require_group_admin(db, current_user)
    svc = GroupService(db)
    await svc.soft_delete(group_id)


async def _require_group_admin(db: AsyncSession, user: User) -> None:
    """Require change_group_settings permission or superuser."""
    if user.is_superuser:
        return
    acl = ACLService(db)
    allowed = await acl.check_permission(user, "change_group_settings", "groups")
    if not allowed:
        raise AuthorizationError("Permission 'change_group_settings' required")
