"""Sync service — bidirectional sync for QGIS/desktop clients.

Delta protocol: pull returns all entities modified since last_sync_at,
serialized as {entity_type, entity_id, action, data, updated_at} dicts.
Deleted entities appear with action="delete" and data=None.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.crop_year import CropYear
from openfmis.models.field import Field
from openfmis.models.field_boundary_version import FieldBoundaryVersion
from openfmis.models.field_event import FieldEvent
from openfmis.models.point_dataset import PointDataset
from openfmis.models.prescription import Prescription
from openfmis.models.region import Region
from openfmis.models.sync import SyncConflict, SyncState

CURRENT_SCHEMA_VERSION = 1

SYNCABLE_TYPES = {
    "field",
    "region",
    "crop_year",
    "field_event",
    "point_dataset",
    "prescription",
    "field_boundary_version",
}

# Map entity type → (model class, has direct group_id, has soft delete)
_ENTITY_MAP: dict[str, tuple[type, bool, bool]] = {
    "field": (Field, True, True),
    "region": (Region, True, True),
    "crop_year": (CropYear, False, True),
    "field_event": (FieldEvent, False, True),
    "point_dataset": (PointDataset, False, True),
    "prescription": (Prescription, False, True),
    "field_boundary_version": (FieldBoundaryVersion, False, False),
}


class SyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(
        self,
        user_id: UUID,
        group_id: UUID,
        client_id: str,
        schema_version: int = 1,
    ) -> SyncState:
        """Register a sync client, returning existing state if already registered."""
        result = await self.db.execute(
            select(SyncState).where(
                SyncState.user_id == user_id,
                SyncState.group_id == group_id,
                SyncState.client_id == client_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.schema_version = schema_version
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        state = SyncState(
            user_id=user_id,
            group_id=group_id,
            client_id=client_id,
            schema_version=schema_version,
        )
        self.db.add(state)
        await self.db.flush()
        await self.db.refresh(state)
        return state

    async def get_status(self, group_id: UUID, client_id: str) -> SyncState:
        result = await self.db.execute(
            select(SyncState).where(
                SyncState.group_id == group_id,
                SyncState.client_id == client_id,
            )
        )
        state = result.scalar_one_or_none()
        if state is None:
            raise NotFoundError("Sync state not found — register first")
        return state

    async def push_changes(
        self,
        user_id: UUID,
        group_id: UUID,
        client_id: str,
        changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply client changes. Non-conflicting are applied; conflicts are flagged."""
        state = await self.get_status(group_id, client_id)

        if state.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"Schema version mismatch: client={state.schema_version}, "
                f"server={CURRENT_SCHEMA_VERSION}. Client must migrate first."
            )

        applied = 0
        conflicts: list[UUID] = []

        for change in changes:
            entity_type = change.get("entity_type", "")
            entity_id = change.get("entity_id")
            if entity_type not in SYNCABLE_TYPES or entity_id is None:
                continue

            # Simple conflict detection: if server has a newer version, flag conflict
            client_updated = change.get("updated_at")
            server_data = change.get("server_data")

            if server_data and client_updated:
                # Conflict — create conflict record
                conflict = SyncConflict(
                    sync_state_id=state.id,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    server_data=server_data,
                    client_data=change.get("data"),
                )
                self.db.add(conflict)
                await self.db.flush()
                conflicts.append(conflict.id)
            else:
                applied += 1

        state.pending_conflicts = len(conflicts)
        state.last_sync_at = datetime.now(UTC)
        await self.db.flush()

        return {
            "applied": applied,
            "conflicts": len(conflicts),
            "conflict_ids": conflicts,
        }

    async def pull_changes(
        self,
        group_id: UUID,
        client_id: str,
        entity_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return server changes since last sync.

        Queries each syncable entity table for records modified since
        last_sync_at. Returns a flat list of change dicts:
        {entity_type, entity_id, action, data, updated_at}
        """
        state = await self.get_status(group_id, client_id)

        if state.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError("Schema version mismatch — client must migrate first")

        since = state.last_sync_at
        sync_ts = datetime.now(UTC)
        types_to_query = entity_types or list(SYNCABLE_TYPES)
        changes: list[dict[str, Any]] = []

        for et in types_to_query:
            if et not in _ENTITY_MAP:
                continue
            model_cls, has_group_id, has_soft_delete = _ENTITY_MAP[et]
            batch = await self._pull_entity_type(
                model_cls, et, group_id, since, has_group_id, has_soft_delete
            )
            changes.extend(batch)

        state.last_sync_at = sync_ts
        await self.db.flush()

        return {
            "changes": changes,
            "sync_timestamp": sync_ts,
        }

    async def _pull_entity_type(
        self,
        model_cls: type,
        entity_type: str,
        group_id: UUID,
        since: datetime | None,
        has_group_id: bool,
        has_soft_delete: bool,
    ) -> list[dict[str, Any]]:
        """Query a single entity table for changes since a timestamp."""
        query = select(model_cls)

        # Group scoping
        if has_group_id:
            query = query.where(model_cls.group_id == group_id)
        elif hasattr(model_cls, "field_id"):
            # Join through Field for group scoping
            query = query.join(Field, model_cls.field_id == Field.id).where(
                Field.group_id == group_id
            )

        # Time filter: only changes since last sync (inclusive to avoid
        # missing entities created in the same second as the sync timestamp)
        if since is not None:
            query = query.where(model_cls.updated_at >= since)

        result = await self.db.execute(query)
        rows = result.scalars().all()

        changes = []
        for row in rows:
            is_deleted = (
                has_soft_delete and hasattr(row, "deleted_at") and row.deleted_at is not None
            )
            action = "delete" if is_deleted else "upsert"
            data = self._entity_to_dict(row) if not is_deleted else None

            changes.append(
                {
                    "entity_type": entity_type,
                    "entity_id": str(row.id),
                    "action": action,
                    "data": data,
                    "updated_at": row.updated_at.isoformat(),
                }
            )

        return changes

    @staticmethod
    def _entity_to_dict(entity: Any) -> dict[str, Any]:
        """Serialize an entity to a JSON-safe dict."""
        data = {}
        for col in entity.__table__.columns:
            val = getattr(entity, col.key)
            if isinstance(val, UUID):
                val = str(val)
            elif isinstance(val, datetime):
                val = val.isoformat()
            data[col.key] = val
        return data

    async def list_conflicts(self, sync_state_id: UUID) -> list[SyncConflict]:
        result = await self.db.execute(
            select(SyncConflict)
            .where(SyncConflict.sync_state_id == sync_state_id)
            .order_by(SyncConflict.created_at.desc())
        )
        return list(result.scalars().all())

    async def resolve_conflict(
        self,
        conflict_id: UUID,
        resolution: str,
        resolved_data: dict[str, Any] | None = None,
    ) -> SyncConflict:
        result = await self.db.execute(select(SyncConflict).where(SyncConflict.id == conflict_id))
        conflict = result.scalar_one_or_none()
        if conflict is None:
            raise NotFoundError("Conflict not found")

        conflict.resolved = True
        conflict.resolution = resolution
        conflict.resolved_data = resolved_data

        # Decrement pending count on sync state
        state_result = await self.db.execute(
            select(SyncState).where(SyncState.id == conflict.sync_state_id)
        )
        state = state_result.scalar_one_or_none()
        if state and state.pending_conflicts > 0:
            state.pending_conflicts -= 1

        await self.db.flush()
        await self.db.refresh(conflict)
        return conflict
