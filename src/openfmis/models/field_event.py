"""FieldEvent + FieldEventEntry models — 9 event types with versioned sub-entries."""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class EventType(StrEnum):
    """The 9 legacy fielddata event types."""

    CROP_PROTECTION = "crop_protection"
    FERTILIZING = "fertilizing"
    HARVEST = "harvest"
    IRRIGATION = "irrigation"
    INSURANCE = "insurance"
    PLANTING = "planting"
    SCOUTING = "scouting"
    SOIL_TESTING = "soil_testing"
    TILLAGE = "tillage"


class FieldEvent(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A field data event — replaces all legacy `fielddata_*` tables.

    All 9 event types share this table with an `event_type` discriminator.
    Type-specific data goes in JSONB `data` column.
    """

    __tablename__ = "field_events"

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fields.id"), nullable=False, index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        Enum(EventType, name="event_type_enum", create_constraint=True),
        nullable=False,
        index=True,
    )
    crop_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    operation_date: Mapped[uuid.UUID | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Versioning via supersedes_id chain (same pattern as Field)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_events.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Type-specific data as JSONB
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Flexible notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    entries: Mapped[list["FieldEventEntry"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )


class FieldEventEntry(Base, UUIDMixin, TimestampMixin):
    """Sub-entries for events (e.g. products, test entries, scouting details).

    Replaces legacy sub-tables like:
    - fielddata_crop_protection_products
    - fielddata_fertilizing_products
    - fielddata_soiltesting_testentries
    - fielddata_scouting_* (beneficials, diseases, insects, weeds, crop_growth, custom)
    - fielddata_insurance_prevented_planting
    """

    __tablename__ = "field_event_entries"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "product", "test_entry", "scouting_insects", "prevented_planting"
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Entry-specific data as JSONB
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    event: Mapped["FieldEvent"] = relationship(back_populates="entries")
