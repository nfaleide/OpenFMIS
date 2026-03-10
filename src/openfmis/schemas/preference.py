"""Preference CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PreferenceRead(BaseModel):
    id: UUID
    user_id: UUID
    namespace: str
    data: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PreferenceUpsert(BaseModel):
    """Create or update a preference (upsert by user_id + namespace)."""

    namespace: str = Field(..., min_length=1, max_length=100)
    data: dict


class PreferenceList(BaseModel):
    items: list[PreferenceRead]
