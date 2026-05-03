"""Equipment CRUD endpoints with group-scoped ACL enforcement."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.schemas.equipment import (
    EquipmentCreate,
    EquipmentList,
    EquipmentRead,
    EquipmentUpdate,
)
from openfmis.services.acl import ACLService
from openfmis.services.equipment import EquipmentService

router = APIRouter(prefix="/equipment", tags=["equipment"])


async def _check_group_settings(
    db: AsyncSession,
    user: User,
    group_id: UUID | None = None,
) -> None:
    """Check change_group_settings permission, raising 403 if denied."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, "change_group_settings", "groups", group_id)
    if not allowed:
        raise AuthorizationError("Permission 'change_group_settings' denied on 'groups'")


def _check_group_membership(user: User, group_id: UUID) -> None:
    """Verify user belongs to the equipment's group."""
    if user.is_superuser:
        return
    if user.group_id != group_id:
        raise AuthorizationError("Equipment belongs to a different group")


@router.get("", response_model=EquipmentList, summary="List equipment")
async def list_equipment(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = None,
    equipment_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> EquipmentList:
    # Non-superusers only see their own group's equipment
    if not current_user.is_superuser:
        group_id = current_user.group_id

    svc = EquipmentService(db)
    equipment, total = await svc.list_equipment(
        group_id=group_id,
        equipment_type=equipment_type,
        offset=offset,
        limit=limit,
    )
    return EquipmentList(
        items=[EquipmentRead.model_validate(e) for e in equipment],
        total=total,
    )


@router.get("/{equip_id}", response_model=EquipmentRead, summary="Get equipment")
async def get_equipment(
    equip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    svc = EquipmentService(db)
    equip = await svc.get_by_id(equip_id)
    _check_group_membership(current_user, equip.group_id)
    return EquipmentRead.model_validate(equip)


@router.post("", response_model=EquipmentRead, status_code=201, summary="Create equipment")
async def create_equipment(
    body: EquipmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    await _check_group_settings(db, current_user, body.group_id)
    svc = EquipmentService(db)
    equip = await svc.create_equipment(body, created_by=current_user.id)
    return EquipmentRead.model_validate(equip)


@router.patch("/{equip_id}", response_model=EquipmentRead, summary="Update equipment")
async def update_equipment(
    equip_id: UUID,
    body: EquipmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    svc = EquipmentService(db)
    equip = await svc.get_by_id(equip_id)
    await _check_group_settings(db, current_user, equip.group_id)
    equip = await svc.update_equipment(equip_id, body)
    return EquipmentRead.model_validate(equip)


@router.delete("/{equip_id}", status_code=204, summary="Delete equipment")
async def delete_equipment(
    equip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = EquipmentService(db)
    equip = await svc.get_by_id(equip_id)
    await _check_group_settings(db, current_user, equip.group_id)
    await svc.soft_delete(equip_id)
