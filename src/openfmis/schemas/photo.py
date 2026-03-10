"""Photo CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PhotoRead(BaseModel):
    id: UUID
    uploaded_by: UUID | None = None
    description: str | None = None
    comments: str | None = None
    storage_url: str
    content_type: str | None = None
    file_size_bytes: int | None = None
    object_type: str | None = None
    object_id: UUID | None = None
    field_event_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PhotoCreate(BaseModel):
    storage_url: str = Field(..., max_length=1024)
    description: str | None = None
    comments: str | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    object_type: str | None = None
    object_id: UUID | None = None
    field_event_id: UUID | None = None
    latitude: float | None = None
    longitude: float | None = None


class PhotoUpdate(BaseModel):
    description: str | None = None
    comments: str | None = None


class PhotoList(BaseModel):
    items: list[PhotoRead]
    total: int
