"""CoreDataset model — generic plugin-attached datasets."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class CoreDataset(Base):
    __tablename__ = "core_datasets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plugin_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset_type: Mapped[str] = mapped_column(String(100), nullable=False)
    field_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_core_datasets_plugin_type", "plugin_slug", "dataset_type"),
        Index("idx_core_datasets_field", "field_id"),
    )

    def __repr__(self) -> str:
        return f"<CoreDataset {self.plugin_slug}:{self.dataset_type} field={self.field_id}>"
