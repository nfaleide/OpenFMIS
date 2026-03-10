"""Pydantic schemas for saved classification presets."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

IndexType = Literal["ndvi", "ndwi", "evi", "ndre", "savi"]


class ClassificationCreate(BaseModel):
    name: str = Field(..., max_length=200)
    index_type: IndexType
    num_classes: int = Field(5, ge=2, le=20)
    breakpoints: list[float] = Field(..., description="Sorted list of break values between classes")
    colors: list[str] = Field(..., description="Hex color per class, length = num_classes")
    description: str | None = None


class ClassificationUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    breakpoints: list[float] | None = None
    colors: list[str] | None = None
    num_classes: int | None = Field(None, ge=2, le=20)
    description: str | None = None


class ClassificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    index_type: str
    num_classes: int
    breakpoints: list[float]
    colors: list[str]
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
