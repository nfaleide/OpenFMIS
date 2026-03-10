"""Region model — named groupings of fields (many-to-many)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Region(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A named grouping of fields — replaces legacy `regions` table."""

    __tablename__ = "regions"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("groups.id"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    members: Mapped[list["RegionMember"]] = relationship(
        back_populates="region", cascade="all, delete-orphan", lazy="selectin"
    )


class RegionMember(Base, TimestampMixin):
    """Junction table linking regions to fields — replaces `regions_mapping`."""

    __tablename__ = "region_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fields.id", ondelete="CASCADE"), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("region_id", "field_id", name="uq_region_member"),)

    # Relationships
    region: Mapped["Region"] = relationship(back_populates="members")
