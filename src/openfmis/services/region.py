"""RegionService — CRUD + many-to-many field membership."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.field import Field
from openfmis.models.privilege import GroupPrivilege, PermissionState, UserPrivilege
from openfmis.models.region import Region, RegionMember
from openfmis.models.user import User
from openfmis.schemas.region import AccessibleRegionItem, AccessibleSet, RegionCreate, RegionUpdate

if TYPE_CHECKING:
    from openfmis.services.acl import ACLService


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

    async def list_my_regions(
        self,
        user: User,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Region], list[int], int]:
        """List regions created by the current user."""
        base = select(Region).where(
            Region.deleted_at.is_(None),
            Region.created_by == user.id,
        )
        count_query = (
            select(func.count())
            .select_from(Region)
            .where(Region.deleted_at.is_(None), Region.created_by == user.id)
        )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = base.order_by(Region.name).offset(offset).limit(limit)
        result = await self.db.execute(query)
        regions = list(result.scalars().all())

        member_counts = await self._get_member_counts(regions)
        return regions, member_counts, total

    async def list_visible_regions(
        self,
        user: User,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Region], list[int], int]:
        """List all regions visible to the user via ACL (including group walk).

        Uses get_accessible_set under the hood, then paginates.
        """
        accessible = await self.get_accessible_set(user)
        region_ids = [r.id for r in accessible.regions]

        if not region_ids:
            return [], [], 0

        total = len(region_ids)

        # Paginate
        paginated_ids = region_ids[offset : offset + limit]
        if not paginated_ids:
            return [], [], total

        result = await self.db.execute(
            select(Region)
            .where(Region.id.in_(paginated_ids), Region.deleted_at.is_(None))
            .order_by(Region.name)
        )
        regions = list(result.scalars().all())
        member_counts = await self._get_member_counts(regions)
        return regions, member_counts, total

    async def _get_member_counts(self, regions: list[Region]) -> list[int]:
        """Get member counts for a list of regions."""
        counts = []
        for region in regions:
            mc_result = await self.db.execute(
                select(func.count())
                .select_from(RegionMember)
                .where(RegionMember.region_id == region.id)
            )
            counts.append(mc_result.scalar_one())
        return counts

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

    async def get_total_area_acres(self, region_id: UUID) -> float | None:
        """Sum area_acres of all current, non-deleted member fields."""
        result = await self.db.execute(
            select(func.sum(Field.area_acres))
            .join(RegionMember, Field.id == RegionMember.field_id)
            .where(
                RegionMember.region_id == region_id,
                Field.is_current.is_(True),
                Field.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    # ── Accessible-set algorithm ────────────────────────────────────

    async def get_accessible_set(self, user: User) -> AccessibleSet:
        """Return the full accessible set for a user.

        Port of legacy get_accessible_regions_and_objects().
        Superusers see everything. Regular users see:
        - Fields their group owns where ACL grants fields.read
        - Regions their group owns where ACL grants regions.read
        - Private regions only if they created it or belong to a parent group
        Per-resource DENY overrides are honored.
        """
        from openfmis.services.acl import ACLService
        from openfmis.services.group import GroupService

        acl = ACLService(self.db)

        # 1. Determine accessible field IDs
        accessible_field_ids = await self._get_accessible_field_ids(user, acl)

        # 2. Determine accessible regions
        accessible_regions = await self._get_accessible_regions(user, acl)

        # 3. Filter private regions
        # Private regions visible only to: the creator, or users in ancestor
        # (parent/grandparent) groups — NOT same-group peers.
        if not user.is_superuser:
            group_svc = GroupService(self.db)
            # Get descendant group IDs — if user is in a parent group,
            # they can see private regions in child groups
            descendant_group_ids: set[UUID] = set()
            if user.group_id is not None:
                try:
                    descendants = await group_svc.get_descendants(user.group_id)
                    descendant_group_ids = {d.id for d in descendants}
                except Exception:
                    pass

            accessible_regions = [
                r
                for r in accessible_regions
                if not r.is_private or r.created_by == user.id or r.group_id in descendant_group_ids
            ]

        # 4. Build result: for each region, count accessible fields within it
        region_items = []
        all_field_ids: set[UUID] = set()

        for region in accessible_regions:
            # Get field IDs in this region (primary region_id)
            result = await self.db.execute(
                select(Field.id).where(
                    Field.region_id == region.id,
                    Field.is_current.is_(True),
                    Field.deleted_at.is_(None),
                    Field.id.in_(accessible_field_ids)
                    if accessible_field_ids is not None
                    else True,
                )
            )
            field_ids_in_region = [row[0] for row in result.all()]
            all_field_ids.update(field_ids_in_region)

            region_items.append(
                AccessibleRegionItem(
                    id=region.id,
                    name=region.name,
                    description=region.description,
                    group_id=region.group_id,
                    is_private=region.is_private,
                    field_count=len(field_ids_in_region),
                    field_ids=field_ids_in_region,
                )
            )

        return AccessibleSet(
            regions=region_items,
            total_regions=len(region_items),
            total_fields=len(all_field_ids),
        )

    async def _get_accessible_field_ids(self, user: User, acl: ACLService) -> set[UUID] | None:
        """Return the set of field IDs the user can read, or None for 'all'.

        None means unrestricted (superuser or wildcard GRANT with no per-resource DENYs).
        """
        if user.is_superuser:
            return None  # All fields

        # Check wildcard fields.read
        has_wildcard = await acl.check_permission(user, "fields.read", "fields")

        # Get per-resource DENY overrides on fields
        deny_ids = await self._get_resource_deny_ids(user, "fields", "fields.read")

        if has_wildcard and not deny_ids:
            # Wildcard GRANT, no per-resource DENYs — all fields in user's group
            result = await self.db.execute(
                select(Field.id).where(
                    Field.group_id == user.group_id,
                    Field.is_current.is_(True),
                    Field.deleted_at.is_(None),
                )
            )
            return {row[0] for row in result.all()}

        if has_wildcard and deny_ids:
            # Wildcard GRANT minus specific DENYs
            result = await self.db.execute(
                select(Field.id).where(
                    Field.group_id == user.group_id,
                    Field.is_current.is_(True),
                    Field.deleted_at.is_(None),
                    Field.id.notin_(deny_ids),
                )
            )
            return {row[0] for row in result.all()}

        # No wildcard GRANT — only per-resource GRANTs
        grant_ids = await self._get_resource_grant_ids(user, "fields", "fields.read")
        return grant_ids

    async def _get_accessible_regions(self, user: User, acl: ACLService) -> list[Region]:
        """Return accessible regions for the user."""
        if user.is_superuser:
            result = await self.db.execute(
                select(Region).where(Region.deleted_at.is_(None)).order_by(Region.name)
            )
            return list(result.scalars().all())

        # Check wildcard regions.read
        has_wildcard = await acl.check_permission(user, "regions.read", "regions")

        # Get per-resource DENY overrides
        deny_ids = await self._get_resource_deny_ids(user, "regions", "regions.read")

        if has_wildcard:
            query = select(Region).where(
                Region.group_id == user.group_id,
                Region.deleted_at.is_(None),
            )
            if deny_ids:
                query = query.where(Region.id.notin_(deny_ids))
            query = query.order_by(Region.name)
            result = await self.db.execute(query)
            return list(result.scalars().all())

        # No wildcard — only per-resource GRANTs
        grant_ids = await self._get_resource_grant_ids(user, "regions", "regions.read")
        if not grant_ids:
            return []
        result = await self.db.execute(
            select(Region)
            .where(Region.id.in_(grant_ids), Region.deleted_at.is_(None))
            .order_by(Region.name)
        )
        return list(result.scalars().all())

    async def _get_resource_deny_ids(
        self, user: User, resource_type: str, permission: str
    ) -> set[UUID]:
        """Get resource IDs where the user has an explicit DENY for a permission."""
        deny_ids: set[UUID] = set()

        # User-level DENYs
        result = await self.db.execute(
            select(UserPrivilege).where(
                UserPrivilege.user_id == user.id,
                UserPrivilege.resource_type == resource_type,
                UserPrivilege.resource_id.isnot(None),
            )
        )
        for priv in result.scalars().all():
            state = priv.permissions.get(permission)
            if state == PermissionState.DENY:
                deny_ids.add(priv.resource_id)

        # Group-level DENYs (only if no user-level override)
        if user.group_id is not None:
            result = await self.db.execute(
                select(GroupPrivilege).where(
                    GroupPrivilege.group_id == user.group_id,
                    GroupPrivilege.resource_type == resource_type,
                    GroupPrivilege.resource_id.isnot(None),
                )
            )
            for priv in result.scalars().all():
                state = priv.permissions.get(permission)
                if state == PermissionState.DENY and priv.resource_id not in deny_ids:
                    deny_ids.add(priv.resource_id)

        return deny_ids

    async def _get_resource_grant_ids(
        self, user: User, resource_type: str, permission: str
    ) -> set[UUID]:
        """Get resource IDs where the user has an explicit GRANT for a permission."""
        grant_ids: set[UUID] = set()

        # User-level GRANTs
        result = await self.db.execute(
            select(UserPrivilege).where(
                UserPrivilege.user_id == user.id,
                UserPrivilege.resource_type == resource_type,
                UserPrivilege.resource_id.isnot(None),
            )
        )
        for priv in result.scalars().all():
            state = priv.permissions.get(permission)
            if state == PermissionState.GRANT:
                grant_ids.add(priv.resource_id)

        # Group-level GRANTs
        if user.group_id is not None:
            result = await self.db.execute(
                select(GroupPrivilege).where(
                    GroupPrivilege.group_id == user.group_id,
                    GroupPrivilege.resource_type == resource_type,
                    GroupPrivilege.resource_id.isnot(None),
                )
            )
            for priv in result.scalars().all():
                state = priv.permissions.get(permission)
                if state == PermissionState.GRANT and priv.resource_id not in grant_ids:
                    grant_ids.add(priv.resource_id)

        return grant_ids

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
