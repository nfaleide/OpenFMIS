"""PointDataset + PointCleaningLog schemas."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

VALID_DATASET_TYPES = {
    "soil_test",
    "yield",
    "as_applied_fert",
    "as_applied_chem",
    "planting",
    "tillage",
    "ec_em",
    "custom",
}

VALID_CLEANING_RULES = {
    "iqr",
    "stddev",
    "percentile",
    "minmax",
    "spatial_dedup",
    "edge_buffer",
}


class PointDatasetCreate(BaseModel):
    field_id: UUID
    crop_year_id: UUID | None = None
    dataset_type: str = Field(..., max_length=50)
    label: str = Field(..., max_length=255)
    value_column: str | None = Field(None, max_length=100)
    unit: str | None = Field(None, max_length=50)
    sample_date: date | None = None
    source_file: str | None = Field(None, max_length=500)
    raw_layer: str | None = None
    clean_layer: str | None = None
    raw_count: int | None = None
    clean_count: int | None = None
    soil_lab: str | None = None
    soil_extractant: str | None = None
    primary_nutrient: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class PointDatasetUpdate(BaseModel):
    label: str | None = Field(None, max_length=255)
    value_column: str | None = Field(None, max_length=100)
    unit: str | None = Field(None, max_length=50)
    sample_date: date | None = None
    raw_count: int | None = None
    clean_count: int | None = None
    soil_lab: str | None = None
    soil_extractant: str | None = None
    primary_nutrient: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class CleaningLogCreate(BaseModel):
    rule_type: str = Field(..., max_length=50)
    parameters: dict[str, Any] | None = None
    points_removed: int = 0


class CleaningLogOut(BaseModel):
    id: UUID
    dataset_id: UUID
    rule_type: str
    parameters: dict[str, Any] | None
    points_removed: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PointDatasetOut(BaseModel):
    id: UUID
    field_id: UUID
    crop_year_id: UUID | None
    dataset_type: str
    label: str
    value_column: str | None
    unit: str | None
    sample_date: date | None
    source_file: str | None
    raw_layer: str | None
    clean_layer: str | None
    raw_count: int | None
    clean_count: int | None
    soil_lab: str | None
    soil_extractant: str | None
    primary_nutrient: str | None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")
    cleaning_log: list[CleaningLogOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
