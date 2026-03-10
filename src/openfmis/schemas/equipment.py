"""Equipment CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EquipmentRead(BaseModel):
    id: UUID
    group_id: UUID
    created_by: UUID | None = None
    name: str
    make: str | None = None
    model: str | None = None
    year: int | None = None
    equipment_type: str | None = None
    metadata_: dict | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class EquipmentCreate(BaseModel):
    group_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    make: str | None = None
    model: str | None = None
    year: int | None = Field(None, ge=1900, le=2100)
    equipment_type: str | None = None
    metadata_: dict | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class EquipmentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    make: str | None = None
    model: str | None = None
    year: int | None = Field(None, ge=1900, le=2100)
    equipment_type: str | None = None
    metadata_: dict | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class EquipmentList(BaseModel):
    items: list[EquipmentRead]
    total: int
