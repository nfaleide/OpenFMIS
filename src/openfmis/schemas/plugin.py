"""Pydantic schemas for Plugin registry."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PluginRegister(BaseModel):
    slug: str = Field(..., max_length=100, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., max_length=200)
    version: str = Field(..., max_length=50)
    description: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)


class PluginUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    version: str | None = Field(None, max_length=50)
    description: str | None = None
    is_active: bool | None = None
    manifest: dict[str, Any] | None = None


class PluginOut(BaseModel):
    id: int
    slug: str
    name: str
    version: str
    description: str | None
    is_active: bool
    manifest: dict[str, Any]
    registered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PluginEventPayload(BaseModel):
    """Payload emitted on plugin lifecycle events."""

    slug: str
    event: str  # "registered" | "activated" | "deactivated" | "updated" | "unregistered"
    manifest: dict[str, Any]
