"""Pydantic schemas for subscriptions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionCreate(BaseModel):
    owner_type: str = Field(..., pattern="^(user|group)$")
    owner_id: uuid.UUID
    plugin_id: str = Field(..., min_length=1, max_length=100)
    subscription_type: str = Field(..., min_length=1, max_length=100)
    expires_at: datetime | None = None
    metadata: dict | None = None


class SubscriptionOut(BaseModel):
    id: uuid.UUID
    owner_type: str
    owner_id: uuid.UUID
    plugin_id: str
    subscription_type: str
    status: str
    metadata_: dict | None = None
    started_at: datetime
    expires_at: datetime | None
    renewed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class SubscriptionRenew(BaseModel):
    expires_at: datetime | None = None


class SubscriptionCancel(BaseModel):
    reason: str | None = None
