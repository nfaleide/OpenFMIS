"""FieldBoundaryVersion — permanent geometry history for fields."""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class FieldBoundaryVersion(Base, UUIDMixin, TimestampMixin):
    """Versioned boundary snapshot — no soft delete (permanent history)."""

    __tablename__ = "field_boundary_versions"

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=False,
    )
    area_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    epsg: Mapped[int] = mapped_column(Integer, default=4326, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    field = relationship("Field", lazy="selectin")
    creator = relationship("User", lazy="selectin")
