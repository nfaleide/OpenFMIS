"""Equipment CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.equipment import (
    EquipmentCreate,
    EquipmentList,
    EquipmentRead,
    EquipmentUpdate,
)
from openfmis.services.equipment import EquipmentService

router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.get("", response_model=EquipmentList)
async def list_equipment(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = None,
    equipment_type: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> EquipmentList:
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


@router.get("/{equip_id}", response_model=EquipmentRead)
async def get_equipment(
    equip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    svc = EquipmentService(db)
    equip = await svc.get_by_id(equip_id)
    return EquipmentRead.model_validate(equip)


@router.post("", response_model=EquipmentRead, status_code=201)
async def create_equipment(
    body: EquipmentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    svc = EquipmentService(db)
    equip = await svc.create_equipment(body, created_by=current_user.id)
    return EquipmentRead.model_validate(equip)


@router.patch("/{equip_id}", response_model=EquipmentRead)
async def update_equipment(
    equip_id: UUID,
    body: EquipmentUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> EquipmentRead:
    svc = EquipmentService(db)
    equip = await svc.update_equipment(equip_id, body)
    return EquipmentRead.model_validate(equip)


@router.delete("/{equip_id}", status_code=204)
async def delete_equipment(
    equip_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = EquipmentService(db)
    await svc.soft_delete(equip_id)
