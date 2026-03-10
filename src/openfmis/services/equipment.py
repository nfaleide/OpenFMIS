"""EquipmentService — CRUD for field operation equipment."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.equipment import Equipment
from openfmis.schemas.equipment import EquipmentCreate, EquipmentUpdate


class EquipmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, equip_id: UUID) -> Equipment:
        result = await self.db.execute(
            select(Equipment).where(Equipment.id == equip_id, Equipment.deleted_at.is_(None))
        )
        equip = result.scalar_one_or_none()
        if equip is None:
            raise NotFoundError("Equipment not found")
        return equip

    async def list_equipment(
        self,
        group_id: UUID | None = None,
        equipment_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Equipment], int]:
        query = select(Equipment).where(Equipment.deleted_at.is_(None))
        count_query = (
            select(func.count()).select_from(Equipment).where(Equipment.deleted_at.is_(None))
        )

        if group_id is not None:
            query = query.where(Equipment.group_id == group_id)
            count_query = count_query.where(Equipment.group_id == group_id)

        if equipment_type is not None:
            query = query.where(Equipment.equipment_type == equipment_type)
            count_query = count_query.where(Equipment.equipment_type == equipment_type)

        query = query.order_by(Equipment.name).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        equipment = list(result.scalars().all())
        return equipment, total

    async def create_equipment(
        self, data: EquipmentCreate, created_by: UUID | None = None
    ) -> Equipment:
        equip = Equipment(
            group_id=data.group_id,
            created_by=created_by,
            name=data.name,
            make=data.make,
            model=data.model,
            year=data.year,
            equipment_type=data.equipment_type,
            metadata_=data.metadata_,
        )
        self.db.add(equip)
        await self.db.flush()
        await self.db.refresh(equip)
        return equip

    async def update_equipment(self, equip_id: UUID, data: EquipmentUpdate) -> Equipment:
        equip = await self.get_by_id(equip_id)
        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(equip, attr, value)
        await self.db.flush()
        await self.db.refresh(equip)
        return equip

    async def soft_delete(self, equip_id: UUID) -> None:
        from datetime import UTC, datetime

        equip = await self.get_by_id(equip_id)
        equip.deleted_at = datetime.now(UTC)
        await self.db.flush()
