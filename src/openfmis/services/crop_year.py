"""CropYear service — CRUD for flexible date-range crop periods."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.crop_year import CropYear
from openfmis.schemas.crop_year import CropYearCreate, CropYearUpdate


class CropYearService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, crop_year_id: UUID) -> CropYear:
        result = await self.db.execute(
            select(CropYear).where(CropYear.id == crop_year_id, CropYear.deleted_at.is_(None))
        )
        cy = result.scalar_one_or_none()
        if cy is None:
            raise NotFoundError("Crop year not found")
        return cy

    async def list_by_field(self, field_id: UUID) -> list[CropYear]:
        result = await self.db.execute(
            select(CropYear)
            .where(CropYear.field_id == field_id, CropYear.deleted_at.is_(None))
            .order_by(CropYear.start_date.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: CropYearCreate) -> CropYear:
        cy = CropYear(
            field_id=data.field_id,
            label=data.label,
            start_date=data.start_date,
            end_date=data.end_date,
            crop_code=data.crop_code,
            tillage=data.tillage,
            planting_date=data.planting_date,
            harvest_date=data.harvest_date,
            notes=data.notes,
            metadata_=data.metadata_,
        )
        self.db.add(cy)
        await self.db.flush()
        await self.db.refresh(cy)
        return cy

    async def update(self, crop_year_id: UUID, data: CropYearUpdate) -> CropYear:
        cy = await self.get_by_id(crop_year_id)
        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(cy, attr, value)
        await self.db.flush()
        await self.db.refresh(cy)
        return cy

    async def soft_delete(self, crop_year_id: UUID) -> None:
        from datetime import UTC, datetime

        cy = await self.get_by_id(crop_year_id)
        cy.deleted_at = datetime.now(UTC)
        await self.db.flush()
