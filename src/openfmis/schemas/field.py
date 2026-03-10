"""Field CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FieldRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    area_acres: float | None = None
    group_id: UUID
    created_by: UUID | None = None
    supersedes_id: UUID | None = None
    version: int
    is_current: bool
    metadata_: dict | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class FieldReadWithGeometry(FieldRead):
    """Includes GeoJSON geometry — use for single-field detail responses."""

    geometry_geojson: dict | None = None


class FieldCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    group_id: UUID
    geometry_geojson: dict | None = None  # GeoJSON dict
    metadata_: dict | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class FieldUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    metadata_: dict | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class FieldList(BaseModel):
    items: list[FieldRead]
    total: int


class FieldVersionHistory(BaseModel):
    """Version chain for a field — newest first."""

    versions: list[FieldRead]
