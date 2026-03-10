"""Pydantic schemas for VRA prescription generation."""

import uuid

from pydantic import BaseModel, Field


class PrescriptionZone(BaseModel):
    zone_name: str
    min_value: float
    max_value: float
    target_rate: float
    unit: str = "lbs/ac"


class TGTRequest(BaseModel):
    job_id: uuid.UUID
    zones: list[PrescriptionZone] = Field(..., min_length=1)


class FODMRequest(BaseModel):
    job_id: uuid.UUID
    base_rate: float = Field(..., gt=0)
    rate_adjustment: float
    num_zones: int = Field(5, ge=2, le=20)
    unit: str = "lbs/ac"


class BMPRequest(BaseModel):
    job_id: uuid.UUID
    breakpoints: list[float] = Field(..., min_length=1)
    rates: list[float] = Field(..., min_length=2)
    unit: str = "lbs/ac"
