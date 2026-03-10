"""Logo CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LogoRead(BaseModel):
    id: UUID
    group_id: UUID
    storage_url: str
    file_type: str | None = None
    width: int | None = None
    height: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LogoUpsert(BaseModel):
    """Create or update a group logo (one logo per group)."""

    group_id: UUID
    storage_url: str = Field(..., max_length=1024)
    file_type: str | None = Field(None, max_length=20)
    width: int | None = None
    height: int | None = None
