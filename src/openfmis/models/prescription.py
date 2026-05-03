"""InterpolationSurface + Prescription models."""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class InterpolationSurface(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "interpolation_surfaces"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("point_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    cell_size_m: Mapped[float] = mapped_column(Float, nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    layer_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    dataset = relationship("PointDataset", lazy="selectin")
    field = relationship("Field", lazy="selectin")


class Prescription(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "prescriptions"

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    crop_year_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crop_years.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zones: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=True,
    )
    source_surface_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interpolation_surfaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    rec_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    export_formats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    field = relationship("Field", lazy="selectin")
    crop_year = relationship("CropYear", lazy="selectin")
    source_surface = relationship("InterpolationSurface", lazy="selectin")
