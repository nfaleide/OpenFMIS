"""Pydantic schemas for zone editing operations."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ZoneMergeRequest(BaseModel):
    zone_ids: list[uuid.UUID] = Field(..., min_length=2)
    merged_name: str = Field(..., max_length=200)


class ZonePaintRequest(BaseModel):
    geometry: dict[str, Any] = Field(..., description="GeoJSON geometry to union with zone")


class ZoneDissolveRequest(BaseModel):
    zone_ids: list[uuid.UUID] = Field(..., min_length=2)


class ZoneSplitRequest(BaseModel):
    split_line: dict[str, Any] = Field(..., description="GeoJSON LineString to split the zone")


class ZoneBufferRequest(BaseModel):
    distance_meters: float = Field(
        ..., description="Buffer distance in meters (negative to shrink)"
    )
