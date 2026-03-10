"""Field event CRUD + versioning + sub-entry endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
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
from openfmis.services.field_event import FieldEventService

router = APIRouter(prefix="/field-events", tags=["field-events"])


@router.get("", response_model=FieldEventList)
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


@router.get("/{event_id}", response_model=FieldEventReadWithEntries)
async def get_event(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventReadWithEntries:
    svc = FieldEventService(db)
    event = await svc.get_by_id(event_id)
    entries = await svc.get_entries(event_id)
    data = FieldEventRead.model_validate(event).model_dump()
    data["entries"] = [FieldEventEntryRead.model_validate(e) for e in entries]
    return FieldEventReadWithEntries(**data)


@router.get("/{event_id}/versions", response_model=FieldEventVersionHistory)
async def get_event_versions(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventVersionHistory:
    svc = FieldEventService(db)
    versions = await svc.get_version_history(event_id)
    return FieldEventVersionHistory(versions=[FieldEventRead.model_validate(v) for v in versions])


@router.post("", response_model=FieldEventRead, status_code=201)
async def create_event(
    body: FieldEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    svc = FieldEventService(db)
    event = await svc.create_event(body, created_by=current_user.id)
    return FieldEventRead.model_validate(event)


@router.patch("/{event_id}", response_model=FieldEventRead)
async def update_event(
    event_id: UUID,
    body: FieldEventUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    svc = FieldEventService(db)
    event = await svc.update_event(event_id, body)
    return FieldEventRead.model_validate(event)


@router.post("/{event_id}/versions", response_model=FieldEventRead, status_code=201)
async def create_event_version(
    event_id: UUID,
    body: FieldEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventRead:
    """Create a new version of an event (supersedes the old one)."""
    svc = FieldEventService(db)
    event = await svc.create_new_version(event_id, body)
    return FieldEventRead.model_validate(event)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = FieldEventService(db)
    await svc.soft_delete(event_id)


# ── Sub-entry endpoints ────────────────────────────────────────


@router.post("/{event_id}/entries", response_model=FieldEventEntryRead, status_code=201)
async def add_entry(
    event_id: UUID,
    body: FieldEventEntryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldEventEntryRead:
    svc = FieldEventService(db)
    entry = await svc.add_entry(event_id, body)
    return FieldEventEntryRead.model_validate(entry)


@router.delete("/entries/{entry_id}", status_code=204)
async def remove_entry(
    entry_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = FieldEventService(db)
    await svc.remove_entry(entry_id)
