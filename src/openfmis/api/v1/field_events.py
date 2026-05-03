"""Field event CRUD + versioning + sub-entry endpoints with ACL enforcement."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.field_event import EventType
from openfmis.models.user import User
from openfmis.schemas.field_event import (
    FieldEventCreate,
    FieldEventEntryCreate,
    FieldEventEntryRead,
    FieldEventList,
    FieldEventRead,
    FieldEventReadWithEntries,
    FieldEventUpdate,
    FieldEventVersionHistory,
)
from openfmis.services.acl import ACLService
from openfmis.services.field_event import FieldEventService

router = APIRouter(prefix="/field-events", tags=["field-events"])


async def _check_fielddata_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: UUID | None = None,
) -> None:
    """Check a fielddata.* permission, raising 403 if denied."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, permission, "fielddata", resource_id)
    if not allowed:
        raise AuthorizationError(f"Permission '{permission}' denied on 'fielddata'")


@router.get("", response_model=FieldEventList, summary="List events")
async def list_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
    event_type: EventType | None = None,
    crop_year: int | None = None,
    current_only: bool = True,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> FieldEventList:
    acl = ACLService(db)
    if not current_user.is_superuser:
        allowed = await acl.check_permission(current_user, "fielddata.read", "fielddata")
        if not allowed:
            return FieldEventList(items=[], total=0)

    svc = FieldEventService(db)
    events, total = await svc.list_events(
        field_id=field_id,
        event_type=event_type,
        crop_year=crop_year,
        current_only=current_only,
        offset=offset,
        limit=limit,
    )
    return FieldEventList(
        items=[FieldEventRead.model_validate(e) for e in events],
        total=total,
    )


@router.get("/{event_id}", response_model=FieldEventReadWithEntries, summary="Get event")
async def get_event(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventReadWithEntries:
    await _check_fielddata_permission(db, current_user, "fielddata.read")
    svc = FieldEventService(db)
    event = await svc.get_by_id(event_id)
    entries = await svc.get_entries(event_id)
    data = FieldEventRead.model_validate(event).model_dump()
    data["entries"] = [FieldEventEntryRead.model_validate(e) for e in entries]
    return FieldEventReadWithEntries(**data)


@router.get(
    "/{event_id}/versions",
    response_model=FieldEventVersionHistory,
    summary="Get event versions",
)
async def get_event_versions(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventVersionHistory:
    await _check_fielddata_permission(db, current_user, "fielddata.read")
    svc = FieldEventService(db)
    versions = await svc.get_version_history(event_id)
    return FieldEventVersionHistory(versions=[FieldEventRead.model_validate(v) for v in versions])


@router.get(
    "/{event_id}/history",
    response_model=FieldEventVersionHistory,
    summary="Get event history",
)
async def get_event_history(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventVersionHistory:
    """Walk the supersedes chain and return all versions chronologically."""
    await _check_fielddata_permission(db, current_user, "fielddata.read")
    svc = FieldEventService(db)
    versions = await svc.get_version_history(event_id)
    # Chronological order (oldest first)
    versions.sort(key=lambda v: v.version)
    return FieldEventVersionHistory(versions=[FieldEventRead.model_validate(v) for v in versions])


@router.post("", response_model=FieldEventRead, status_code=201, summary="Create event")
async def create_event(
    body: FieldEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    await _check_fielddata_permission(db, current_user, "fielddata.append")
    svc = FieldEventService(db)
    event = await svc.create_event(body, created_by=current_user.id)
    return FieldEventRead.model_validate(event)


@router.patch("/{event_id}", response_model=FieldEventRead, summary="Update event")
async def update_event(
    event_id: UUID,
    body: FieldEventUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    await _check_fielddata_permission(db, current_user, "fielddata.modify")
    svc = FieldEventService(db)
    event = await svc.update_event(event_id, body)
    return FieldEventRead.model_validate(event)


@router.post(
    "/{event_id}/versions",
    response_model=FieldEventRead,
    status_code=201,
    summary="Create event version",
)
async def create_event_version(
    event_id: UUID,
    body: FieldEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    """Create a new version of an event (supersedes the old one)."""
    await _check_fielddata_permission(db, current_user, "fielddata.modify")
    svc = FieldEventService(db)
    event = await svc.create_new_version(event_id, body)
    return FieldEventRead.model_validate(event)


@router.delete("/{event_id}", status_code=204, summary="Delete event")
async def delete_event(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _check_fielddata_permission(db, current_user, "fielddata.modify")
    svc = FieldEventService(db)
    await svc.soft_delete(event_id)


# ── Sub-entry endpoints ────────────────────────────────────────


@router.post(
    "/{event_id}/entries",
    response_model=FieldEventEntryRead,
    status_code=201,
    summary="Add entry",
)
async def add_entry(
    event_id: UUID,
    body: FieldEventEntryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventEntryRead:
    await _check_fielddata_permission(db, current_user, "fielddata.modify")
    svc = FieldEventService(db)
    entry = await svc.add_entry(event_id, body)
    return FieldEventEntryRead.model_validate(entry)


@router.delete("/entries/{entry_id}", status_code=204, summary="Remove entry")
async def remove_entry(
    entry_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await _check_fielddata_permission(db, current_user, "fielddata.modify")
    svc = FieldEventService(db)
    await svc.remove_entry(entry_id)
