"""Sampling plan models — persistent field sampling with generated points."""

import uuid
from enum import StrEnum

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


def _enum_values(enum_cls):
    return [x.value for x in enum_cls]


class SamplingAlgorithm(StrEnum):
    RANDOM = "random"
    GRID = "grid"
    CLUSTERED = "clustered"
    W = "w"
    SSUS = "ssus"


class SamplingPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class SamplingPlan(Base, UUIDMixin, TimestampMixin):
    """A collection of sample points generated for a field or zone."""

    __tablename__ = "sampling_plans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    algorithm: Mapped[SamplingAlgorithm] = mapped_column(
        Enum(SamplingAlgorithm, name="sampling_algorithm_enum", values_callable=_enum_values),
        nullable=False,
    )
    status: Mapped[SamplingPlanStatus] = mapped_column(
        Enum(SamplingPlanStatus, name="sampling_plan_status_enum", values_callable=_enum_values),
        nullable=False,
        server_default="draft",
        index=True,
    )

    # Algorithm parameters
    point_count: Mapped[int] = mapped_column(Integer, nullable=False)
    min_distance: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    buffer_distance: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    cluster_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_cluster_distance: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Generated sample points stored as PostGIS MultiPoint
    points: Mapped[object | None] = mapped_column(
        Geometry("MULTIPOINT", srid=4326),
        nullable=True,
    )
    # Also store as GeoJSON for easy API serialisation
    points_geojson: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Navigation / field collection tracking
    points_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    collection_notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    field = relationship("Field", lazy="selectin")
    creator = relationship("User", lazy="selectin")

    __table_args__ = (
        CheckConstraint("point_count >= 1 AND point_count <= 999", name="ck_sampling_point_count"),
        CheckConstraint("min_distance >= 0", name="ck_sampling_min_distance"),
        CheckConstraint("buffer_distance >= 0", name="ck_sampling_buffer_distance"),
        CheckConstraint("points_completed >= 0", name="ck_sampling_points_completed"),
        CheckConstraint(
            "status IN ('draft', 'active', 'in_progress', 'completed', 'archived')",
            name="ck_sampling_plan_status",
        ),
        CheckConstraint(
            "algorithm IN ('random', 'grid', 'clustered', 'w', 'ssus')",
            name="ck_sampling_algorithm",
        ),
        Index("idx_sampling_plans_field_status", "field_id", "status"),
    )
