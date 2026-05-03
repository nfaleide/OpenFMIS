"""Region CRUD schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RegionRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    group_id: UUID
    created_by: UUID | None = None
    is_private: bool
    metadata_: dict | None = Field(None, alias="metadata_")
    field_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class RegionAccessibility(BaseModel):
    """What the requesting user can do with this region."""

    can_read: bool = True
    can_modify: bool = False
    can_delete: bool = False


class RegionReadWithFields(RegionRead):
    """Includes field IDs of members, total area, and accessibility."""

    field_ids: list[UUID] = []
    total_area_acres: float | None = None
    accessibility: RegionAccessibility | None = None


class RegionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    group_id: UUID
    is_private: bool = False
    metadata_: dict | None = Field(None, alias="metadata_")
    field_ids: list[UUID] = []  # Optional: add fields on creation

    model_config = {"populate_by_name": True}


class RegionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_private: bool | None = None
    metadata_: dict | None = Field(None, alias="metadata_")

    model_config = {"populate_by_name": True}


class RegionMemberAdd(BaseModel):
    """Add fields to a region."""

    field_ids: list[UUID] = Field(..., min_length=1)


class RegionMemberRemove(BaseModel):
    """Remove fields from a region."""

    field_ids: list[UUID] = Field(..., min_length=1)


class RegionList(BaseModel):
    items: list[RegionRead]
    total: int


class AccessibleRegionItem(BaseModel):
    """A region with its accessible field count and field IDs."""

    id: UUID
    name: str
    description: str | None = None
    group_id: UUID
    is_private: bool
    field_count: int
    field_ids: list[UUID]


class AccessibleSet(BaseModel):
    """Full accessible set for a user: regions + fields + counts."""

    regions: list[AccessibleRegionItem]
    total_regions: int
    total_fields: int
