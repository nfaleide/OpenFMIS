"""Plugin SDK — Dataset attachment.

Plugins attach datasets (analysis results, scene caches, etc.) to fields
via this module. The underlying storage is the ``core_datasets`` table.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.core_dataset import CoreDataset


async def attach_dataset(
    db: AsyncSession,
    *,
    plugin_slug: str,
    dataset_type: str,
    field_id: UUID | None = None,
    metadata: dict | None = None,
    storage_url: str | None = None,
    created_by: UUID | None = None,
) -> CoreDataset:
    """Create a new dataset record attached to a field (or global)."""
    ds = CoreDataset(
        plugin_slug=plugin_slug,
        dataset_type=dataset_type,
        field_id=field_id,
        extra_metadata=metadata or {},
        storage_url=storage_url,
        created_by=created_by,
    )
    db.add(ds)
    await db.flush()
    await db.refresh(ds)
    return ds


async def get_dataset(db: AsyncSession, dataset_id: UUID) -> CoreDataset:
    """Get a single dataset by ID. Raises NotFoundError if missing or deleted."""
    result = await db.execute(
        select(CoreDataset).where(
            CoreDataset.id == dataset_id,
            CoreDataset.deleted_at.is_(None),
        )
    )
    ds = result.scalar_one_or_none()
    if ds is None:
        raise NotFoundError("Dataset not found")
    return ds


async def list_datasets_for_field(
    db: AsyncSession,
    field_id: UUID,
    plugin_slug: str | None = None,
    dataset_type: str | None = None,
) -> list[CoreDataset]:
    """List datasets attached to a field, optionally filtered."""
    query = select(CoreDataset).where(
        CoreDataset.field_id == field_id,
        CoreDataset.deleted_at.is_(None),
    )
    if plugin_slug is not None:
        query = query.where(CoreDataset.plugin_slug == plugin_slug)
    if dataset_type is not None:
        query = query.where(CoreDataset.dataset_type == dataset_type)
    query = query.order_by(CoreDataset.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_dataset(db: AsyncSession, dataset_id: UUID) -> None:
    """Soft-delete a dataset."""
    from datetime import UTC, datetime

    ds = await get_dataset(db, dataset_id)
    ds.deleted_at = datetime.now(UTC)
    await db.flush()
