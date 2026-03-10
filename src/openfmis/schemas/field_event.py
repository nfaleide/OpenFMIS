"""FieldEvent CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

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
