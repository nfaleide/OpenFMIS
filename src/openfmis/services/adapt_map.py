"""ADAPT entity mapping service — CRUD + lookup."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.adapt_map import ADAPTEntityMap
from openfmis.schemas.adapt_map import ADAPTMapCreate, ADAPTMapUpsert


class ADAPTMapService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, map_id: UUID) -> ADAPTEntityMap:
        result = await self.db.execute(select(ADAPTEntityMap).where(ADAPTEntityMap.id == map_id))
        m = result.scalar_one_or_none()
        if m is None:
            raise NotFoundError("ADAPT mapping not found")
        return m

    async def list_by_type(self, internal_type: str) -> list[ADAPTEntityMap]:
        result = await self.db.execute(
            select(ADAPTEntityMap)
            .where(ADAPTEntityMap.internal_type == internal_type)
            .order_by(ADAPTEntityMap.created_at.desc())
        )
        return list(result.scalars().all())

    async def lookup(self, internal_type: str, internal_id: UUID) -> ADAPTEntityMap | None:
        result = await self.db.execute(
            select(ADAPTEntityMap).where(
                ADAPTEntityMap.internal_type == internal_type,
                ADAPTEntityMap.internal_id == internal_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: ADAPTMapCreate) -> ADAPTEntityMap:
        m = ADAPTEntityMap(
            internal_type=data.internal_type,
            internal_id=data.internal_id,
            adapt_type=data.adapt_type,
            adapt_id=data.adapt_id,
            adapt_role=data.adapt_role,
            metadata_=data.metadata_,
        )
        self.db.add(m)
        await self.db.flush()
        await self.db.refresh(m)
        return m

    async def upsert(self, data: ADAPTMapUpsert) -> ADAPTEntityMap:
        existing = await self.lookup(data.internal_type, data.internal_id)
        if existing is not None:
            existing.adapt_type = data.adapt_type
            existing.adapt_id = data.adapt_id
            existing.adapt_role = data.adapt_role
            existing.metadata_ = data.metadata_
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        return await self.create(
            ADAPTMapCreate(
                internal_type=data.internal_type,
                internal_id=data.internal_id,
                adapt_type=data.adapt_type,
                adapt_id=data.adapt_id,
                adapt_role=data.adapt_role,
                metadata_=data.metadata_,
            )
        )

    async def delete(self, map_id: UUID) -> None:
        m = await self.get_by_id(map_id)
        await self.db.delete(m)
        await self.db.flush()
