"""FieldEvent CRUD schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from openfmis.models.field_event import EventType


class FieldEventEntryRead(BaseModel):
    id: UUID
    event_id: UUID
    entry_type: str
    sort_order: int
    data: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldEventEntryCreate(BaseModel):
    entry_type: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0
    data: dict | None = None


class FieldEventRead(BaseModel):
    id: UUID
    field_id: UUID
    event_type: EventType
    crop_year: int
    operation_date: datetime | None = None
    created_by: UUID | None = None
    supersedes_id: UUID | None = None
    version: int
    is_current: bool
    data: dict | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FieldEventReadWithEntries(FieldEventRead):
    """Includes sub-entries."""

    entries: list[FieldEventEntryRead] = []


class FieldEventCreate(BaseModel):
    field_id: UUID
    event_type: EventType
    crop_year: int = Field(..., ge=1900, le=2100)
    operation_date: datetime | None = None
    data: dict | None = None
    notes: str | None = None
    entries: list[FieldEventEntryCreate] = []


class FieldEventUpdate(BaseModel):
    """Update event data (non-versioned update).

    For geometry/structural changes, use versioned update.
    """

    data: dict | None = None
    notes: str | None = None
    operation_date: datetime | None = None


class FieldEventList(BaseModel):
    items: list[FieldEventRead]
    total: int


class FieldEventVersionHistory(BaseModel):
    versions: list[FieldEventRead]


# ── Per-subtype data schemas ──────────────────────────────────


class ProductApplication(BaseModel):
    """Shared product application model for crop_protection and fertilizing."""

    product: str = Field(..., min_length=1, max_length=255)
    rate: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1, max_length=50)
    additional_attribs: dict | None = None


# Task #14: planting, crop_protection, harvest


class PlantingEventData(BaseModel):
    """Planting event data — seed variety, rates, spacing."""

    crop: str = Field(..., min_length=1, max_length=100)
    variety: str | None = None
    seed_rate: float | None = None
    seed_rate_unit: str | None = None
    population: float | None = None
    row_spacing: float | None = None
    row_spacing_unit: str | None = None
    additional_attribs: dict | None = None


class CropProtectionEventData(BaseModel):
    """Crop protection event data — target pest + product list."""

    target_pest: str | None = None
    products: list[ProductApplication] = Field(default_factory=list)
    additional_attribs: dict | None = None


class HarvestEventData(BaseModel):
    """Harvest event data — yield, moisture, test weight."""

    crop: str = Field(..., min_length=1, max_length=100)
    yield_amount: float = Field(..., ge=0)
    yield_unit: str = Field(..., min_length=1, max_length=50)
    moisture: float | None = Field(None, ge=0, le=100)
    test_weight: float | None = None
    additional_attribs: dict | None = None


# Task #16: fertilizing


class FertilizingEventData(BaseModel):
    """Fertilizing event data — product applications."""

    products: list[ProductApplication] = Field(..., min_length=1)
    additional_attribs: dict | None = None


# Task #17: scouting (6 subtypes — entries go in FieldEventEntry rows)


class ScoutingEventData(BaseModel):
    """Scouting event data — high-level metadata.

    Individual scouting observations go in FieldEventEntry rows with
    entry_type in {beneficials, diseases, insects, weeds, crop_growth, custom}.
    """

    scout_name: str | None = None
    growth_stage: str | None = None
    additional_attribs: dict | None = None


# Task #18: soil_testing


class SoilTestEntry(BaseModel):
    """A single soil test result with plausibility ranges."""

    parameter: str = Field(..., min_length=1, max_length=100)
    value: float
    unit: str = Field("", max_length=50)
    depth: float | None = None
    depth_unit: str | None = None


class ValidationIssue(BaseModel):
    parameter: str
    value: float
    message: str


class SoilTestEventData(BaseModel):
    """Soil testing event data with test entries and validation."""

    lab_name: str | None = None
    sample_date: datetime | None = None
    test_entries: list[SoilTestEntry] = Field(..., min_length=1)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    additional_attribs: dict | None = None

    @model_validator(mode="after")
    def check_plausibility(self) -> "SoilTestEventData":
        """Warn (don't reject) on out-of-range soil test values."""
        ranges: dict[str, tuple[float, float]] = {
            "pH": (3.5, 9.5),
            "P": (0, 500),  # ppm
            "K": (20, 1000),  # ppm
            "OM": (0, 20),  # percent
            "CEC": (1, 80),  # meq/100g
            "S": (0, 100),  # ppm
            "Zn": (0, 50),  # ppm
            "Mn": (0, 200),  # ppm
            "Fe": (0, 500),  # ppm
            "Cu": (0, 30),  # ppm
            "B": (0, 10),  # ppm
        }
        issues = list(self.validation_issues)
        for entry in self.test_entries:
            param = entry.parameter
            if param in ranges:
                lo, hi = ranges[param]
                if not lo <= entry.value <= hi:
                    issues.append(
                        ValidationIssue(
                            parameter=param,
                            value=entry.value,
                            message=f"{param} value {entry.value} outside "
                            f"plausible range [{lo}, {hi}]",
                        )
                    )
        self.validation_issues = issues
        return self


# Task #19: tillage, irrigation, insurance


class TillageType(StrEnum):
    NO_TILL = "no_till"
    STRIP_TILL = "strip_till"
    MIN_TILL = "min_till"
    CHISEL = "chisel"
    DISK = "disk"
    MOLDBOARD = "moldboard"
    VERTICAL = "vertical"
    UNKNOWN = "unknown"


class TillageEventData(BaseModel):
    """Tillage event data."""

    tillage_type: TillageType
    depth: float | None = None
    depth_unit: str | None = None
    additional_attribs: dict | None = None


class IrrigationEventData(BaseModel):
    """Irrigation event data."""

    volume: float = Field(..., gt=0)
    volume_unit: str = Field(..., min_length=1, max_length=50)
    method: str | None = None
    additional_attribs: dict | None = None


class PreventedPlanting(BaseModel):
    """Prevented planting block for insurance events."""

    reason: str = Field(..., min_length=1)
    acres_affected: float = Field(..., ge=0)
    intended_crop: str | None = None


class InsuranceEventData(BaseModel):
    """Insurance event data."""

    fcic_crop_code: str = Field(..., min_length=1, max_length=20)
    policy_number: str | None = None
    coverage_level: float | None = None
    prevented_planting: PreventedPlanting | None = None
    additional_attribs: dict | None = None


# ── Dispatch map: event_type → schema ─────────────────────────

EVENT_DATA_SCHEMAS: dict[EventType, type[BaseModel]] = {
    EventType.PLANTING: PlantingEventData,
    EventType.CROP_PROTECTION: CropProtectionEventData,
    EventType.HARVEST: HarvestEventData,
    EventType.FERTILIZING: FertilizingEventData,
    EventType.SCOUTING: ScoutingEventData,
    EventType.SOIL_TESTING: SoilTestEventData,
    EventType.TILLAGE: TillageEventData,
    EventType.IRRIGATION: IrrigationEventData,
    EventType.INSURANCE: InsuranceEventData,
}


def validate_event_data(event_type: EventType, data: dict | None) -> dict | None:
    """Validate event data against the subtype schema.

    Returns the validated (and potentially enriched) data dict, or raises
    ValidationError if required fields are missing.
    """
    if data is None:
        return None

    schema = EVENT_DATA_SCHEMAS.get(event_type)
    if schema is None:
        return data  # No schema defined — pass through

    validated = schema.model_validate(data)
    return validated.model_dump(mode="json")
