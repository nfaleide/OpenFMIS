"""Pydantic schemas for the Sampling plugin."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ── Create / Update ──────────────────────────────────────────────────────────


class SamplingPlanCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    field_id: UUID
    zone_id: UUID | None = None
    algorithm: str = Field(..., pattern=r"^(random|grid|clustered|w|ssus)$")
    point_count: int = Field(..., ge=1, le=999)
    min_distance: float = Field(default=0.0, ge=0)
    buffer_distance: float = Field(default=0.0, ge=0)
    cluster_count: int | None = Field(default=None, ge=2, le=50)
    min_cluster_distance: float | None = Field(default=None, ge=0)


class SamplingPlanUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    status: str | None = Field(None, pattern=r"^(draft|active|in_progress|completed|archived)$")
    points_completed: int | None = Field(None, ge=0)
    collection_notes: dict[str, Any] | None = None


class SamplingPlanRegenerate(BaseModel):
    """Re-generate points with optionally updated parameters."""

    point_count: int | None = Field(None, ge=1, le=999)
    algorithm: str | None = Field(None, pattern=r"^(random|grid|clustered|w|ssus)$")
    min_distance: float | None = Field(None, ge=0)
    buffer_distance: float | None = Field(None, ge=0)
    cluster_count: int | None = Field(None, ge=2, le=50)
    min_cluster_distance: float | None = Field(None, ge=0)


# ── Responses ────────────────────────────────────────────────────────────────


class SamplingPlanOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    field_id: UUID
    zone_id: UUID | None
    created_by: UUID
    algorithm: str
    status: str
    point_count: int
    min_distance: float
    buffer_distance: float
    cluster_count: int | None
    min_cluster_distance: float | None
    points_geojson: dict[str, Any] | None
    points_completed: int
    collection_notes: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SamplingPlanSummary(BaseModel):
    id: UUID
    name: str
    field_id: UUID
    algorithm: str
    status: str
    point_count: int
    points_completed: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Auto-Zone from Index ─────────────────────────────────────────────────────


class AutoZoneRequest(BaseModel):
    """Create zones from analysis job results by thresholding an index."""

    field_id: UUID
    job_id: UUID
    zone_count: int = Field(default=3, ge=2, le=10)
    method: str = Field(
        default="quantile",
        pattern=r"^(quantile|equal_interval|manual)$",
    )
    thresholds: list[float] | None = None
    name_prefix: str = Field(default="Zone", max_length=100)


class AutoZoneOut(BaseModel):
    zones: list[dict[str, Any]]
    thresholds: list[float]
    index_type: str


# ── Multi-Zone Batch Sampling ────────────────────────────────────────────────


class BatchSamplingRequest(BaseModel):
    """Generate sampling plans for all zones in a field at once."""

    field_id: UUID
    algorithm: str = Field(..., pattern=r"^(random|grid|clustered|w|ssus)$")
    points_per_zone: int = Field(..., ge=1, le=999)
    min_distance: float = Field(default=0.0, ge=0)
    buffer_distance: float = Field(default=0.0, ge=0)
    cluster_count: int | None = Field(default=None, ge=2, le=50)
    min_cluster_distance: float | None = Field(default=None, ge=0)
    name_template: str = Field(
        default="{zone_name} Sampling",
        max_length=200,
    )


class BatchSamplingOut(BaseModel):
    plans: list[SamplingPlanOut]
    total_points: int


# ── Point-Level Index Extraction ─────────────────────────────────────────────


class PointExtractionRequest(BaseModel):
    """Extract index values at each sampling point location."""

    plan_id: UUID
    scene_id: str
    index_type: str = Field(default="ndvi", max_length=50)
    collection: str = Field(default="sentinel-2-l2a", max_length=50)


class PointIndexValue(BaseModel):
    point_index: int
    lng: float
    lat: float
    value: float | None
    completed: bool


class PointExtractionOut(BaseModel):
    plan_id: UUID
    scene_id: str
    index_type: str
    points: list[PointIndexValue]
    stats: dict[str, Any]


# ── Export ───────────────────────────────────────────────────────────────────


class ExportPointFeature(BaseModel):
    point_id: int
    planned_lng: float
    planned_lat: float
    status: str
    completed: bool
    notes: str | None


class ExportOut(BaseModel):
    plan_name: str
    format: str
    point_count: int
    completed_count: int
    content: str
