"""Pydantic schemas for scene notifications."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    scene_id: str
    field_id: uuid.UUID
    notification_type: str
    message: str | None
    metadata_: dict | None = Field(None, alias="metadata")
    viewed: bool
    visible: bool
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class NotificationPreferenceOut(BaseModel):
    user_id: uuid.UUID
    email_enabled: bool
    scene_types: dict | None
    settings: dict | None

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    scene_types: dict | None = None
    settings: dict | None = None


class MarkViewedRequest(BaseModel):
    notification_ids: list[uuid.UUID] = Field(..., min_length=1)


class SetVisibilityRequest(BaseModel):
    notification_ids: list[uuid.UUID] = Field(..., min_length=1)
    visible: bool
