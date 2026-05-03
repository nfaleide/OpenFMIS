"""PointDataset + PointCleaningLog — spatial point data management."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class PointDataset(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "point_datasets"

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
    dataset_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    value_column: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sample_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_layer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clean_layer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clean_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soil_lab: Mapped[str | None] = mapped_column(String(255), nullable=True)
    soil_extractant: Mapped[str | None] = mapped_column(String(100), nullable=True)
    primary_nutrient: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    field = relationship("Field", lazy="selectin")
    crop_year = relationship("CropYear", lazy="selectin")
    cleaning_log: Mapped[list["PointCleaningLog"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PointCleaningLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "point_cleaning_log"

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("point_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    points_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    dataset: Mapped["PointDataset"] = relationship(back_populates="cleaning_log")
