"""Satshot imagery models — scene cache, analysis zones, analysis jobs."""

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base


class SceneRecord(Base):
    """Cached Sentinel-2 STAC scene metadata."""

    __tablename__ = "scene_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scene_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    collection: Mapped[str] = mapped_column(String(100), nullable=False, default="sentinel-2-l2a")
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cloud_cover: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    assets: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stac_properties: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    footprint: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    cached_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_scene_acquired", "acquired_at"),
        Index("idx_scene_cloud", "cloud_cover"),
    )

    def __repr__(self) -> str:
        return f"<SceneRecord {self.scene_id}>"


class AnalysisZone(Base):
    """Sub-field polygon used as the AOI for targeted analysis."""

    __tablename__ = "analysis_zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fields.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="zone", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_analysis_zones_field", "field_id"),)

    def __repr__(self) -> str:
        return f"<AnalysisZone {self.name} field={self.field_id}>"


class AnalysisJob(Base):
    """A single index-computation job over a field (or zone) + scene."""

    __tablename__ = "analysis_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fields.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_zones.id", ondelete="SET NULL"), nullable=True
    )
    scene_id: Mapped[str] = mapped_column(String(200), nullable=False)
    index_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    zone: Mapped["AnalysisZone | None"] = relationship("AnalysisZone", back_populates="jobs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="ck_analysis_job_status",
        ),
        Index("idx_analysis_jobs_field", "field_id"),
        Index("idx_analysis_jobs_status", "status"),
        Index("idx_analysis_jobs_scene", "scene_id"),
    )

    def __repr__(self) -> str:
        return f"<AnalysisJob {self.index_type} {self.status}>"
