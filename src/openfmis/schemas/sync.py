"""Sync schemas — registration, push/pull, conflict resolution."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SyncRegisterRequest(BaseModel):
    group_id: UUID
    client_id: str = Field(..., max_length=255)
    schema_version: int = 1


class SyncStatusOut(BaseModel):
    id: UUID
    user_id: UUID
    group_id: UUID
    client_id: str
    last_sync_at: datetime | None
    schema_version: int
    pending_conflicts: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncPushRequest(BaseModel):
    group_id: UUID
    client_id: str
    changes: list[dict[str, Any]]


class SyncPushOut(BaseModel):
    applied: int
    conflicts: int
    conflict_ids: list[UUID]


class SyncPullRequest(BaseModel):
    group_id: UUID
    client_id: str
    entity_types: list[str] | None = None


class SyncPullOut(BaseModel):
    changes: list[dict[str, Any]]
    sync_timestamp: datetime


class SyncConflictOut(BaseModel):
    id: UUID
    sync_state_id: UUID
    entity_type: str
    entity_id: UUID
    server_data: dict[str, Any] | None
    client_data: dict[str, Any] | None
    resolved: bool
    resolution: str | None
    resolved_data: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncConflictResolveRequest(BaseModel):
    resolution: str = Field(..., pattern=r"^(server_wins|client_wins|merged)$")
    resolved_data: dict[str, Any] | None = None
