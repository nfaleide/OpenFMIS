"""CropYear model — flexible date-range periods for a field (ADAPT: CropZone)."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class CropYear(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "crop_years"

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    crop_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tillage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    planting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    field = relationship("Field", lazy="selectin")
