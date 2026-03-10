"""Group CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GroupRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    parent_id: UUID | None = None
    settings: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GroupReadWithChildren(GroupRead):
    """Group with nested children for tree responses."""

    children: list["GroupReadWithChildren"] = []


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    parent_id: UUID | None = None
    settings: dict | None = None


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    parent_id: UUID | None = None
    settings: dict | None = None


class GroupList(BaseModel):
    items: list[GroupRead]
    total: int


class GroupAncestry(BaseModel):
    """Flat list of ancestors from root → leaf."""

    ancestors: list[GroupRead]
