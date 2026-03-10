"""FieldEventService — CRUD with versioning and sub-entries for 9 event types."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.field_event import EventType, FieldEvent, FieldEventEntry
from openfmis.schemas.field_event import (
    FieldEventCreate,
    FieldEventEntryCreate,
    FieldEventUpdate,
)


class FieldEventService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, event_id: UUID, include_deleted: bool = False) -> FieldEvent:
        query = select(FieldEvent).where(FieldEvent.id == event_id)
        if not include_deleted:
            query = query.where(FieldEvent.deleted_at.is_(None))
        result = await self.db.execute(query)
        event = result.scalar_one_or_none()
        if event is None:
            raise NotFoundError("Field event not found")
        return event

    async def list_events(
        self,
        field_id: UUID | None = None,
        event_type: EventType | None = None,
        crop_year: int | None = None,
        current_only: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[FieldEvent], int]:
        query = select(FieldEvent).where(FieldEvent.deleted_at.is_(None))
        count_query = (
            select(func.count()).select_from(FieldEvent).where(FieldEvent.deleted_at.is_(None))
        )

        if current_only:
            query = query.where(FieldEvent.is_current.is_(True))
            count_query = count_query.where(FieldEvent.is_current.is_(True))

        if field_id is not None:
            query = query.where(FieldEvent.field_id == field_id)
            count_query = count_query.where(FieldEvent.field_id == field_id)

        if event_type is not None:
            query = query.where(FieldEvent.event_type == event_type)
            count_query = count_query.where(FieldEvent.event_type == event_type)

        if crop_year is not None:
            query = query.where(FieldEvent.crop_year == crop_year)
            count_query = count_query.where(FieldEvent.crop_year == crop_year)

        query = query.order_by(FieldEvent.created_at.desc()).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        events = list(result.scalars().all())
        return events, total

    async def create_event(
        self, data: FieldEventCreate, created_by: UUID | None = None
    ) -> FieldEvent:
        event = FieldEvent(
            field_id=data.field_id,
            event_type=data.event_type,
            crop_year=data.crop_year,
            operation_date=data.operation_date,
            created_by=created_by,
            version=1,
            is_current=True,
            data=data.data,
            notes=data.notes,
        )
        self.db.add(event)
        await self.db.flush()

        # Add sub-entries
        for entry_data in data.entries:
            entry = FieldEventEntry(
                event_id=event.id,
                entry_type=entry_data.entry_type,
                sort_order=entry_data.sort_order,
                data=entry_data.data,
            )
            self.db.add(entry)

        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def update_event(self, event_id: UUID, data: FieldEventUpdate) -> FieldEvent:
        """Non-versioned update — updates metadata/notes in place."""
        event = await self.get_by_id(event_id)

        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(event, attr, value)

        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def create_new_version(self, event_id: UUID, data: FieldEventCreate) -> FieldEvent:
        """Create a new version of an event (supersedes the old one)."""
        old_event = await self.get_by_id(event_id)

        # Mark old as non-current
        old_event.is_current = False
        await self.db.flush()

        # Create new version
        new_event = FieldEvent(
            field_id=old_event.field_id,
            event_type=old_event.event_type,
            crop_year=data.crop_year,
            operation_date=data.operation_date,
            created_by=old_event.created_by,
            supersedes_id=old_event.id,
            version=old_event.version + 1,
            is_current=True,
            data=data.data,
            notes=data.notes,
        )
        self.db.add(new_event)
        await self.db.flush()

        # Add new sub-entries
        for entry_data in data.entries:
            entry = FieldEventEntry(
                event_id=new_event.id,
                entry_type=entry_data.entry_type,
                sort_order=entry_data.sort_order,
                data=entry_data.data,
            )
            self.db.add(entry)

        await self.db.flush()
        await self.db.refresh(new_event)
        return new_event

    async def get_version_history(self, event_id: UUID) -> list[FieldEvent]:
        """Get all versions in the chain, newest first."""
        current = await self.get_by_id(event_id, include_deleted=True)

        # Walk back to root
        root = current
        while root.supersedes_id is not None:
            result = await self.db.execute(
                select(FieldEvent).where(FieldEvent.id == root.supersedes_id)
            )
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            root = parent

        # Collect forward from root
        versions = [root]
        seen = {root.id}

        while True:
            result = await self.db.execute(
                select(FieldEvent).where(
                    FieldEvent.supersedes_id.in_(
                        [v.id for v in versions if v.id not in seen or v.id == versions[-1].id]
                    ),
                    FieldEvent.id.notin_(seen),
                )
            )
            next_versions = list(result.scalars().all())
            if not next_versions:
                break
            for v in next_versions:
                seen.add(v.id)
                versions.append(v)

        versions.sort(key=lambda e: e.version, reverse=True)
        return versions

    async def soft_delete(self, event_id: UUID) -> None:
        from datetime import UTC, datetime

        event = await self.get_by_id(event_id)
        event.deleted_at = datetime.now(UTC)
        event.is_current = False
        await self.db.flush()

    # ── Sub-entry management ───────────────────────────────────────

    async def add_entry(self, event_id: UUID, entry: FieldEventEntryCreate) -> FieldEventEntry:
        await self.get_by_id(event_id)  # Validate event exists
        new_entry = FieldEventEntry(
            event_id=event_id,
            entry_type=entry.entry_type,
            sort_order=entry.sort_order,
            data=entry.data,
        )
        self.db.add(new_entry)
        await self.db.flush()
        await self.db.refresh(new_entry)
        return new_entry

    async def remove_entry(self, entry_id: UUID) -> None:
        result = await self.db.execute(
            select(FieldEventEntry).where(FieldEventEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            raise NotFoundError("Event entry not found")
        await self.db.delete(entry)
        await self.db.flush()

    async def get_entries(self, event_id: UUID) -> list[FieldEventEntry]:
        result = await self.db.execute(
            select(FieldEventEntry)
            .where(FieldEventEntry.event_id == event_id)
            .order_by(FieldEventEntry.sort_order)
        )
        return list(result.scalars().all())
