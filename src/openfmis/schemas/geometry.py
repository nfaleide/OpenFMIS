"""Geometry operation schemas — input/output for PostGIS spatial ops."""

from uuid import UUID

from pydantic import BaseModel, Field


class GeometryValidation(BaseModel):
    """Result of ST_IsValid check."""

    is_valid: bool
    reason: str | None = None  # ST_IsValidReason if invalid


class GeometryArea(BaseModel):
    """Area calculation result."""

    area_acres: float
    area_sq_meters: float


class GeometryType(BaseModel):
    """Geometry type info."""

    geometry_type: str  # e.g. "MULTIPOLYGON", "POLYGON", "POINT"
    num_geometries: int  # Number of parts in multi-geometry


class GeometryInput(BaseModel):
    """GeoJSON geometry input."""

    geometry: dict  # GeoJSON dict


class MultiGeometryInput(BaseModel):
    """Multiple GeoJSON geometries for merge/union."""

    geometries: list[dict] = Field(..., min_length=2)


class ClipInput(BaseModel):
    """Input for intersection/clip operation."""

    geometry: dict  # The geometry to clip
    clip_geometry: dict  # The clipping boundary


class HoleInput(BaseModel):
    """Input for symmetric difference (hole-punching) operation."""

    geometry: dict  # The outer geometry
    hole_geometry: dict  # The geometry to subtract


class BufferInput(BaseModel):
    """Input for buffer operation."""

    geometry: dict  # GeoJSON geometry to buffer
    distance_meters: float = Field(..., gt=0, le=100000)  # Buffer distance in meters


class IntersectionQuery(BaseModel):
    """Query for finding intersecting fields."""

    geometry: dict  # GeoJSON geometry to check against
    group_id: UUID | None = None  # Optional: limit to fields in this group


class IntersectionResult(BaseModel):
    """A field that intersects the query geometry."""

    field_id: UUID
    field_name: str
    intersection_area_acres: float | None = None
    overlap_percent: float | None = None  # % of query geometry covered


class IntersectionResponse(BaseModel):
    """Response for intersection query."""

    intersecting_fields: list[IntersectionResult]
    total: int


class CentroidResponse(BaseModel):
    """Centroid of a geometry."""

    longitude: float
    latitude: float


class BboxResponse(BaseModel):
    """Bounding box of a geometry."""

    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float
    area_acres: float
