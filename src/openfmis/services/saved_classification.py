"""SavedClassificationService — CRUD for user classification presets."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.saved_classification import SavedClassification
from openfmis.schemas.saved_classification import ClassificationCreate, ClassificationUpdate


class ClassificationNotFoundError(Exception):
    pass


class SavedClassificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, user_id: uuid.UUID, data: ClassificationCreate) -> SavedClassification:
        _validate_consistency(data.num_classes, data.breakpoints, data.colors)
        record = SavedClassification(
            user_id=user_id,
            name=data.name,
            index_type=data.index_type,
            num_classes=data.num_classes,
            breakpoints=data.breakpoints,
            colors=data.colors,
            description=data.description,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def list_for_user(
        self, user_id: uuid.UUID, index_type: str | None = None
    ) -> list[SavedClassification]:
        stmt = select(SavedClassification).where(SavedClassification.user_id == user_id)
        if index_type:
            stmt = stmt.where(SavedClassification.index_type == index_type)
        stmt = stmt.order_by(SavedClassification.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, classification_id: uuid.UUID) -> SavedClassification | None:
        result = await self.db.execute(
            select(SavedClassification).where(SavedClassification.id == classification_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, classification_id: uuid.UUID, data: ClassificationUpdate
    ) -> SavedClassification:
        record = await self.get(classification_id)
        if record is None:
            raise ClassificationNotFoundError(str(classification_id))

        if data.name is not None:
            record.name = data.name
        if data.description is not None:
            record.description = data.description
        if data.num_classes is not None:
            record.num_classes = data.num_classes
        if data.breakpoints is not None:
            record.breakpoints = data.breakpoints
        if data.colors is not None:
            record.colors = data.colors

        # Re-validate consistency after partial update
        _validate_consistency(record.num_classes, record.breakpoints, record.colors)

        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def rename(self, classification_id: uuid.UUID, new_name: str) -> SavedClassification:
        record = await self.get(classification_id)
        if record is None:
            raise ClassificationNotFoundError(str(classification_id))
        record.name = new_name
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def delete(self, classification_id: uuid.UUID) -> None:
        record = await self.get(classification_id)
        if record is None:
            raise ClassificationNotFoundError(str(classification_id))
        await self.db.delete(record)
        await self.db.flush()


def _validate_consistency(num_classes: int, breakpoints: list[float], colors: list[str]) -> None:
    if len(colors) != num_classes:
        raise ValueError(f"colors length ({len(colors)}) must equal num_classes ({num_classes})")
    if len(breakpoints) != num_classes - 1:
        raise ValueError(
            f"breakpoints length ({len(breakpoints)}) must equal "
            f"num_classes - 1 ({num_classes - 1})"
        )
    if breakpoints != sorted(breakpoints):
        raise ValueError("breakpoints must be sorted in ascending order")
