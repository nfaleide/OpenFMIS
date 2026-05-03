"""ADAPT entity mapping schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ADAPTMapCreate(BaseModel):
    internal_type: str = Field(..., max_length=50)
    internal_id: UUID
    adapt_type: str = Field(..., max_length=50)
    adapt_id: UUID
    adapt_role: str | None = Field(None, max_length=50)
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class ADAPTMapUpsert(BaseModel):
    internal_type: str = Field(..., max_length=50)
    internal_id: UUID
    adapt_type: str = Field(..., max_length=50)
    adapt_id: UUID
    adapt_role: str | None = Field(None, max_length=50)
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class ADAPTMapOut(BaseModel):
    id: UUID
    internal_type: str
    internal_id: UUID
    adapt_type: str
    adapt_id: UUID
    adapt_role: str | None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
