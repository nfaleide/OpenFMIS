"""Pydantic schemas for Satshot imagery (scenes, zones, analysis jobs)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# No longer restricted to 5 — any slug from spectral_index_definitions is valid
IndexType = str  # kept as alias for backward compatibility
JobStatus = Literal["pending", "running", "complete", "failed"]


# ── Scene ─────────────────────────────────────────────────────────────────────


class SceneOut(BaseModel):
    id: uuid.UUID
    scene_id: str
    collection: str
    acquired_at: datetime
    cloud_cover: float | None
    bbox: list[float] | None
    assets: dict[str, Any]
    stac_properties: dict[str, Any]
    cached_at: datetime

    model_config = {"from_attributes": True}


class SceneSearchParams(BaseModel):
    geometry: dict[str, Any] = Field(..., description="GeoJSON geometry (Polygon or MultiPolygon)")
    date_from: datetime
    date_to: datetime
    cloud_cover_max: float = Field(30.0, ge=0.0, le=100.0)
    limit: int = Field(10, ge=1, le=100)
    collection: str = "sentinel-2-l2a"
    collections: list[str] | None = None  # multi-source search


# ── Analysis Zone ─────────────────────────────────────────────────────────────


class ZoneCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: str | None = None
    geometry_geojson: dict[str, Any] | None = None  # GeoJSON MultiPolygon


class ZoneUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    geometry_geojson: dict[str, Any] | None = None


class ZoneOut(BaseModel):
    id: uuid.UUID
    field_id: uuid.UUID
    name: str
    description: str | None
    geometry_geojson: dict[str, Any] | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Analysis Job ──────────────────────────────────────────────────────────────


class JobCreate(BaseModel):
    field_id: uuid.UUID
    scene_id: str
    index_type: str = Field(..., max_length=50)
    zone_id: uuid.UUID | None = None
    collection: str = "sentinel-2-l2a"


class JobOut(BaseModel):
    id: uuid.UUID
    field_id: uuid.UUID
    zone_id: uuid.UUID | None
    scene_id: str
    index_type: IndexType
    status: JobStatus
    result: dict[str, Any] | None
    error_message: str | None
    credits_consumed: int
    created_by: uuid.UUID | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AnalysisResult(BaseModel):
    """Statistics returned in job.result."""

    mean: float | None
    min: float | None
    max: float | None
    std: float | None
    p10: float | None
    p90: float | None
    pixel_count: int
    valid_pixel_count: int
    nodata_fraction: float
