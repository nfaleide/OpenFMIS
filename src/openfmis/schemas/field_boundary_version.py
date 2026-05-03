"""FieldBoundaryVersion schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BoundaryVersionCreate(BaseModel):
    field_id: UUID
    geometry_geojson: dict
    source: str | None = None
    epsg: int = 4326
    created_by: UUID | None = None


class BoundaryVersionOut(BaseModel):
    id: UUID
    field_id: UUID
    area_acres: float | None
    source: str | None
    epsg: int
    version: int
    is_current: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BoundaryVersionDetail(BoundaryVersionOut):
    geometry_geojson: dict | None = None
