"""RegionService — CRUD + many-to-many field membership."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.region import Region, RegionMember
from openfmis.schemas.region import RegionCreate, RegionUpdate


class RegionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, region_id: UUID) -> Region:
        result = await self.db.execute(
            select(Region).where(Region.id == region_id, Region.deleted_at.is_(None))
        )
        region = result.scalar_one_or_none()
        if region is None:
            raise NotFoundError("Region not found")
        return region

    async def list_regions(
        self,
        offset: int = 0,
        limit: int = 50,
        group_id: UUID | None = None,
    ) -> tuple[list[Region], list[int], int]:
        """List regions with member counts.

        Returns (regions, member_counts, total).
        """
        query = select(Region).where(Region.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Region).where(Region.deleted_at.is_(None))

        if group_id is not None:
            query = query.where(Region.group_id == group_id)
            count_query = count_query.where(Region.group_id == group_id)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Region.name).offset(offset).limit(limit)
        result = await self.db.execute(query)
        regions = list(result.scalars().all())

        # Get member counts
        member_counts = []
        for region in regions:
            mc_result = await self.db.execute(
                select(func.count())
                .select_from(RegionMember)
                .where(RegionMember.region_id == region.id)
            )
            member_counts.append(mc_result.scalar_one())

        return regions, member_counts, total

    async def create_region(self, data: RegionCreate, created_by: UUID | None = None) -> Region:
        region = Region(
            name=data.name,
            description=data.description,
            group_id=data.group_id,
            created_by=created_by,
            is_private=data.is_private,
            metadata_=data.metadata_,
        )
        self.db.add(region)
        await self.db.flush()

        # Add initial field memberships
        if data.field_ids:
            await self._add_members(region.id, data.field_ids)

        await self.db.refresh(region)
        return region

    async def update_region(self, region_id: UUID, data: RegionUpdate) -> Region:
        region = await self.get_by_id(region_id)

        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(region, attr, value)

        await self.db.flush()
        await self.db.refresh(region)
        return region

    async def soft_delete(self, region_id: UUID) -> None:
        from datetime import UTC, datetime

        region = await self.get_by_id(region_id)
        region.deleted_at = datetime.now(UTC)
        await self.db.flush()

    # ── Membership management ──────────────────────────────────────

    async def add_members(self, region_id: UUID, field_ids: list[UUID]) -> int:
        """Add fields to region. Returns count of newly added."""
        await self.get_by_id(region_id)  # Ensure region exists
        return await self._add_members(region_id, field_ids)

    async def remove_members(self, region_id: UUID, field_ids: list[UUID]) -> int:
        """Remove fields from region. Returns count removed."""
        await self.get_by_id(region_id)  # Ensure region exists
        result = await self.db.execute(
            delete(RegionMember).where(
                RegionMember.region_id == region_id,
                RegionMember.field_id.in_(field_ids),
            )
        )
        return result.rowcount

    async def get_member_field_ids(self, region_id: UUID) -> list[UUID]:
        """Get all field IDs in a region."""
        result = await self.db.execute(
            select(RegionMember.field_id).where(RegionMember.region_id == region_id)
        )
        return [row[0] for row in result.all()]

    async def get_regions_for_field(self, field_id: UUID) -> list[Region]:
        """Get all regions containing a field."""
        result = await self.db.execute(
            select(Region)
            .join(RegionMember, Region.id == RegionMember.region_id)
            .where(
                RegionMember.field_id == field_id,
                Region.deleted_at.is_(None),
            )
            .order_by(Region.name)
        )
        return list(result.scalars().all())

    async def get_field_count(self, region_id: UUID) -> int:
        """Count fields in a region."""
        result = await self.db.execute(
            select(func.count())
            .select_from(RegionMember)
            .where(RegionMember.region_id == region_id)
        )
        return result.scalar_one()

    # ── Internal ───────────────────────────────────────────────────

    async def _add_members(self, region_id: UUID, field_ids: list[UUID]) -> int:
        """Add fields to region, skipping duplicates. Returns count added."""
        # Get existing members
        existing = await self.db.execute(
            select(RegionMember.field_id).where(
                RegionMember.region_id == region_id,
                RegionMember.field_id.in_(field_ids),
            )
        )
        existing_ids = {row[0] for row in existing.all()}

        added = 0
        for fid in field_ids:
            if fid not in existing_ids:
                self.db.add(RegionMember(region_id=region_id, field_id=fid))
                added += 1

        if added:
            await self.db.flush()
        return added
