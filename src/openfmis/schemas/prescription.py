"""Prescription + InterpolationSurface schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

VALID_INTERPOLATION_METHODS = {
    "idw",
    "kriging_ordinary",
    "kriging_simple",
    "tin",
    "natural_neighbor",
    "rbf",
}

VALID_CLASSIFICATION_METHODS = {
    "equal_interval",
    "quantile",
    "natural_breaks",
    "custom",
}


class InterpolationSurfaceCreate(BaseModel):
    dataset_id: UUID
    field_id: UUID
    method: str = Field(..., max_length=50)
    cell_size_m: float = Field(..., gt=0)
    parameters: dict[str, Any] | None = None
    layer_ref: str | None = None


class InterpolationSurfaceOut(BaseModel):
    id: UUID
    dataset_id: UUID
    field_id: UUID
    method: str
    cell_size_m: float
    parameters: dict[str, Any] | None
    layer_ref: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrescriptionCreate(BaseModel):
    field_id: UUID
    crop_year_id: UUID | None = None
    name: str = Field(..., max_length=255)
    product: str | None = Field(None, max_length=255)
    unit: str | None = Field(None, max_length=50)
    zone_count: int | None = None
    classification: str | None = Field(None, max_length=50)
    zones: dict[str, Any] | None = None
    geometry_geojson: dict | None = None
    source_surface_id: UUID | None = None
    rec_model: str | None = None
    export_formats: dict[str, Any] | None = None
    notes: str | None = None


class PrescriptionUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    product: str | None = Field(None, max_length=255)
    unit: str | None = Field(None, max_length=50)
    zone_count: int | None = None
    classification: str | None = Field(None, max_length=50)
    zones: dict[str, Any] | None = None
    geometry_geojson: dict | None = None
    rec_model: str | None = None
    export_formats: dict[str, Any] | None = None
    notes: str | None = None


class PrescriptionOut(BaseModel):
    id: UUID
    field_id: UUID
    crop_year_id: UUID | None
    name: str
    product: str | None
    unit: str | None
    zone_count: int | None
    classification: str | None
    zones: dict[str, Any] | None
    source_surface_id: UUID | None
    rec_model: str | None
    export_formats: dict[str, Any] | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrescriptionDetail(PrescriptionOut):
    geometry_geojson: dict | None = None
