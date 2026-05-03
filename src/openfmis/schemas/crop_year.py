"""CropYear schemas."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

VALID_TILLAGE_TYPES = {
    "no_till",
    "strip_till",
    "min_till",
    "chisel",
    "disk",
    "moldboard",
    "vertical",
    "unknown",
}


class CropYearCreate(BaseModel):
    field_id: UUID
    label: str = Field(..., max_length=255)
    start_date: date
    end_date: date
    crop_code: int | None = None
    tillage: str | None = Field(None, max_length=50)
    planting_date: date | None = None
    harvest_date: date | None = None
    notes: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.tillage and self.tillage not in VALID_TILLAGE_TYPES:
            raise ValueError(f"tillage must be one of {sorted(VALID_TILLAGE_TYPES)}")
        return self


class CropYearUpdate(BaseModel):
    label: str | None = Field(None, max_length=255)
    start_date: date | None = None
    end_date: date | None = None
    crop_code: int | None = None
    tillage: str | None = Field(None, max_length=50)
    planting_date: date | None = None
    harvest_date: date | None = None
    notes: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class CropYearOut(BaseModel):
    id: UUID
    field_id: UUID
    label: str
    start_date: date
    end_date: date
    crop_code: int | None
    tillage: str | None
    planting_date: date | None
    harvest_date: date | None
    notes: str | None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
