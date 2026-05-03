"""ADAPTEntityMap — bidirectional mapping between OpenFMIS and ADAPT entities."""

import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class ADAPTEntityMap(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "adapt_entity_map"

    internal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    internal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    adapt_type: Mapped[str] = mapped_column(String(50), nullable=False)
    adapt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    adapt_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (Index("ix_adapt_entity_map_internal", "internal_type", "internal_id"),)
