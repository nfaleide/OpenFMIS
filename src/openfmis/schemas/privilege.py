"""Privilege / ACL schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PrivilegeRead(BaseModel):
    id: UUID
    resource_type: str
    resource_id: UUID | None = None
    permissions: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPrivilegeRead(PrivilegeRead):
    user_id: UUID


class GroupPrivilegeRead(PrivilegeRead):
    group_id: UUID


class PrivilegeGrant(BaseModel):
    """Grant or update permissions on a resource."""

    resource_type: str = Field(..., min_length=1, max_length=100)
    resource_id: UUID | None = None
    permissions: dict[str, str] = Field(
        ...,
        description="Map of permission name → state (GRANT, ALLOW, DENY)",
    )


class PermissionCheck(BaseModel):
    """Result of checking a single permission."""

    permission: str
    granted: bool
    source: str | None = None  # "user", "group", "superuser", or None


class EffectivePermissions(BaseModel):
    """All effective permissions for a user on a resource."""

    user_id: UUID
    resource_type: str
    resource_id: UUID | None = None
    permissions: dict[str, str]  # permission → effective state
