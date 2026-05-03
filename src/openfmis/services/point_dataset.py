"""PointDataset service — CRUD for spatial point datasets and cleaning log."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.point_dataset import PointCleaningLog, PointDataset
from openfmis.schemas.point_dataset import (
    CleaningLogCreate,
    PointDatasetCreate,
    PointDatasetUpdate,
)


class PointDatasetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, dataset_id: UUID) -> PointDataset:
        result = await self.db.execute(
            select(PointDataset).where(
                PointDataset.id == dataset_id, PointDataset.deleted_at.is_(None)
            )
        )
        ds = result.scalar_one_or_none()
        if ds is None:
            raise NotFoundError("Point dataset not found")
        return ds

    async def list_datasets(
        self,
        field_id: UUID | None = None,
        dataset_type: str | None = None,
        crop_year_id: UUID | None = None,
    ) -> list[PointDataset]:
        query = select(PointDataset).where(PointDataset.deleted_at.is_(None))
        if field_id is not None:
            query = query.where(PointDataset.field_id == field_id)
        if dataset_type is not None:
            query = query.where(PointDataset.dataset_type == dataset_type)
        if crop_year_id is not None:
            query = query.where(PointDataset.crop_year_id == crop_year_id)
        query = query.order_by(PointDataset.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, data: PointDatasetCreate) -> PointDataset:
        ds = PointDataset(
            field_id=data.field_id,
            crop_year_id=data.crop_year_id,
            dataset_type=data.dataset_type,
            label=data.label,
            value_column=data.value_column,
            unit=data.unit,
            sample_date=data.sample_date,
            source_file=data.source_file,
            raw_layer=data.raw_layer,
            clean_layer=data.clean_layer,
            raw_count=data.raw_count,
            clean_count=data.clean_count,
            soil_lab=data.soil_lab,
            soil_extractant=data.soil_extractant,
            primary_nutrient=data.primary_nutrient,
            metadata_=data.metadata_,
        )
        self.db.add(ds)
        await self.db.flush()
        await self.db.refresh(ds)
        return ds

    async def update(self, dataset_id: UUID, data: PointDatasetUpdate) -> PointDataset:
        ds = await self.get_by_id(dataset_id)
        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(ds, attr, value)
        await self.db.flush()
        await self.db.refresh(ds)
        return ds

    async def soft_delete(self, dataset_id: UUID) -> None:
        from datetime import UTC, datetime

        ds = await self.get_by_id(dataset_id)
        ds.deleted_at = datetime.now(UTC)
        await self.db.flush()

    async def get_cleaning_log(self, dataset_id: UUID) -> list[PointCleaningLog]:
        await self.get_by_id(dataset_id)  # verify exists
        result = await self.db.execute(
            select(PointCleaningLog)
            .where(PointCleaningLog.dataset_id == dataset_id)
            .order_by(PointCleaningLog.created_at)
        )
        return list(result.scalars().all())

    async def add_cleaning_step(
        self,
        dataset_id: UUID,
        data: CleaningLogCreate,
    ) -> PointCleaningLog:
        await self.get_by_id(dataset_id)  # verify exists
        log = PointCleaningLog(
            dataset_id=dataset_id,
            rule_type=data.rule_type,
            parameters=data.parameters,
            points_removed=data.points_removed,
        )
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log
