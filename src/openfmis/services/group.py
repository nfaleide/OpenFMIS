"""GroupService — CRUD + recursive CTE hierarchy queries."""

from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError, ValidationError
from openfmis.models.group import Group
from openfmis.schemas.group import GroupCreate, GroupUpdate


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, group_id: UUID) -> Group:
        result = await self.db.execute(
            select(Group).where(Group.id == group_id, Group.deleted_at.is_(None))
        )
        group = result.scalar_one_or_none()
        if group is None:
            raise NotFoundError("Group not found")
        return group

    async def list_groups(
        self,
        offset: int = 0,
        limit: int = 50,
        parent_id: UUID | None = None,
        root_only: bool = False,
    ) -> tuple[list[Group], int]:
        query = select(Group).where(Group.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Group).where(Group.deleted_at.is_(None))

        if root_only:
            query = query.where(Group.parent_id.is_(None))
            count_query = count_query.where(Group.parent_id.is_(None))
        elif parent_id is not None:
            query = query.where(Group.parent_id == parent_id)
            count_query = count_query.where(Group.parent_id == parent_id)

        query = query.order_by(Group.name).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        groups = list(result.scalars().all())
        return groups, total

    async def create_group(self, data: GroupCreate) -> Group:
        # Validate parent exists
        if data.parent_id is not None:
            await self.get_by_id(data.parent_id)

        group = Group(
            name=data.name,
            description=data.description,
            parent_id=data.parent_id,
            settings=data.settings,
        )
        self.db.add(group)
        await self.db.flush()
        return group

    async def update_group(self, group_id: UUID, data: GroupUpdate) -> Group:
        group = await self.get_by_id(group_id)

        if data.parent_id is not None:
            # Can't be your own parent
            if data.parent_id == group_id:
                raise ValidationError("A group cannot be its own parent")
            # Check for circular reference
            if await self._would_create_cycle(group_id, data.parent_id):
                raise ValidationError("This would create a circular group hierarchy")
            await self.get_by_id(data.parent_id)

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(group, field, value)

        await self.db.flush()
        await self.db.refresh(group)
        return group

    async def soft_delete(self, group_id: UUID) -> None:
        from datetime import UTC, datetime

        group = await self.get_by_id(group_id)
        group.deleted_at = datetime.now(UTC)
        await self.db.flush()

    # ── Recursive CTE queries ──────────────────────────────────────

    async def get_ancestors(self, group_id: UUID) -> list[Group]:
        """Return ancestors from root → immediate parent (recursive CTE)."""
        # Anchor: the group itself
        anchor = (
            select(
                Group.id,
                Group.name,
                Group.parent_id,
                literal_column("0").label("depth"),
            )
            .where(Group.id == group_id, Group.deleted_at.is_(None))
            .cte(name="ancestors", recursive=True)
        )

        # Recursive: join parent
        recursive = (
            select(
                Group.id,
                Group.name,
                Group.parent_id,
                (anchor.c.depth + 1).label("depth"),
            )
            .join(anchor, Group.id == anchor.c.parent_id)
            .where(Group.deleted_at.is_(None))
        )

        cte = anchor.union_all(recursive)

        # Fetch full Group objects for the ancestor IDs (excluding self)
        ancestor_ids_query = select(cte.c.id).where(cte.c.depth > 0).order_by(cte.c.depth.desc())
        ancestor_ids_result = await self.db.execute(ancestor_ids_query)
        ancestor_ids = [row[0] for row in ancestor_ids_result.all()]

        if not ancestor_ids:
            return []

        # Fetch in order
        result = await self.db.execute(select(Group).where(Group.id.in_(ancestor_ids)))
        groups_map = {g.id: g for g in result.scalars().all()}
        return [groups_map[aid] for aid in ancestor_ids if aid in groups_map]

    async def get_descendants(self, group_id: UUID) -> list[Group]:
        """Return all descendants (children, grandchildren, etc.) via recursive CTE."""
        anchor = (
            select(
                Group.id,
                Group.parent_id,
                literal_column("0").label("depth"),
            )
            .where(Group.id == group_id, Group.deleted_at.is_(None))
            .cte(name="descendants", recursive=True)
        )

        recursive = (
            select(
                Group.id,
                Group.parent_id,
                (anchor.c.depth + 1).label("depth"),
            )
            .join(anchor, Group.parent_id == anchor.c.id)
            .where(Group.deleted_at.is_(None))
        )

        cte = anchor.union_all(recursive)

        # All descendants (excluding self)
        desc_ids_query = select(cte.c.id).where(cte.c.depth > 0).order_by(cte.c.depth)
        desc_ids_result = await self.db.execute(desc_ids_query)
        desc_ids = [row[0] for row in desc_ids_result.all()]

        if not desc_ids:
            return []

        result = await self.db.execute(select(Group).where(Group.id.in_(desc_ids)))
        groups_map = {g.id: g for g in result.scalars().all()}
        return [groups_map[did] for did in desc_ids if did in groups_map]

    async def get_tree(self, root_id: UUID | None = None) -> list[dict]:
        """Build a nested tree structure. If root_id=None, returns all root groups."""
        if root_id is not None:
            root = await self.get_by_id(root_id)
            descendants = await self.get_descendants(root_id)
            all_groups = [root] + descendants
        else:
            result = await self.db.execute(
                select(Group).where(Group.deleted_at.is_(None)).order_by(Group.name)
            )
            all_groups = list(result.scalars().all())

        start_parent = root.parent_id if root_id is not None else None
        return self._build_tree(all_groups, start_parent)

    def _build_tree(self, groups: list[Group], root_parent_id: UUID | None) -> list[dict]:
        children_map: dict[UUID | None, list[Group]] = {}
        for g in groups:
            children_map.setdefault(g.parent_id, []).append(g)

        def _recurse(parent_id: UUID | None) -> list[dict]:
            nodes = []
            for g in children_map.get(parent_id, []):
                nodes.append(
                    {
                        "id": g.id,
                        "name": g.name,
                        "description": g.description,
                        "parent_id": g.parent_id,
                        "children": _recurse(g.id),
                    }
                )
            return nodes

        return _recurse(root_parent_id)

    async def _would_create_cycle(self, group_id: UUID, new_parent_id: UUID) -> bool:
        """Check if setting new_parent_id would create a cycle."""
        descendants = await self.get_descendants(group_id)
        descendant_ids = {d.id for d in descendants}
        return new_parent_id in descendant_ids
