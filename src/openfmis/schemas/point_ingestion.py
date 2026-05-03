"""Point ingestion schemas — preview, upload, validate, structured intake."""

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FilePreviewOut(BaseModel):
    lat_column: str | None = None
    lon_column: str | None = None
    geometry_type: str  # "latlon", "geometry", "wkt"
    all_columns: list[str]
    value_columns: list[str]
    suggested_type: str | None = None
    suggested_value_column: str | None = None
    row_count: int
    sample_rows: list[dict[str, Any]]
    crs: str = "EPSG:4326"


class CleaningRuleSpec(BaseModel):
    type: str = Field(..., max_length=50)
    parameters: dict[str, Any] = Field(default_factory=dict)


class StructuredIntakeRequest(BaseModel):
    field_id: UUID
    dataset_type: str = Field(..., max_length=50)
    label: str = Field(..., max_length=255)
    features: list[dict[str, Any]]
    value_column: str | None = None
    unit: str | None = None
    crop_year_id: UUID | None = None
    sample_date: date | None = None
    cleaning_log: list[dict[str, Any]] = Field(default_factory=list)


class StructuredIntakeOut(BaseModel):
    dataset_id: UUID
    raw_count: int
    clean_count: int


class ValidationRequest(BaseModel):
    dataset_type: str
    values: list[dict[str, Any]]
    unit: str | None = None
    check_coordinates: bool = True
    conus_only: bool = False


class ValidationIssue(BaseModel):
    row: int
    column: str
    value: Any
    issue: str


class ValidationOut(BaseModel):
    valid: bool
    total_rows: int
    issues: list[ValidationIssue]
