"""Sync endpoints — bidirectional sync for desktop clients."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, verify_group_access
from openfmis.exceptions import NotFoundError
from openfmis.models.user import User
from openfmis.schemas.sync import (
    SyncConflictOut,
    SyncConflictResolveRequest,
    SyncPullOut,
    SyncPullRequest,
    SyncPushOut,
    SyncPushRequest,
    SyncRegisterRequest,
    SyncStatusOut,
)
from openfmis.services.sync import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/register", response_model=SyncStatusOut, status_code=201, summary="Register sync")
async def register_sync(
    body: SyncRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SyncStatusOut:
    await verify_group_access(current_user, body.group_id)
    svc = SyncService(db)
    state = await svc.register(
        user_id=current_user.id,
        group_id=body.group_id,
        client_id=body.client_id,
        schema_version=body.schema_version,
    )
    return SyncStatusOut.model_validate(state)


@router.get("/status", response_model=SyncStatusOut, summary="Get sync status")
async def get_sync_status(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    group_id: UUID | None = None,
    client_id: str | None = None,
) -> SyncStatusOut:
    if group_id is None or client_id is None:
        raise HTTPException(400, "group_id and client_id are required")
    await verify_group_access(current_user, group_id)
    svc = SyncService(db)
    try:
        state = await svc.get_status(group_id, client_id)
    except NotFoundError:
        raise HTTPException(404, "Sync state not found — register first")
    return SyncStatusOut.model_validate(state)


@router.post("/push", response_model=SyncPushOut, summary="Push changes")
async def push_changes(
    body: SyncPushRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SyncPushOut:
    await verify_group_access(current_user, body.group_id)
    svc = SyncService(db)
    try:
        result = await svc.push_changes(
            user_id=current_user.id,
            group_id=body.group_id,
            client_id=body.client_id,
            changes=body.changes,
        )
    except NotFoundError:
        raise HTTPException(404, "Sync state not found — register first")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return SyncPushOut(**result)


@router.post("/pull", response_model=SyncPullOut, summary="Pull changes")
async def pull_changes(
    body: SyncPullRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SyncPullOut:
    await verify_group_access(current_user, body.group_id)
    svc = SyncService(db)
    try:
        result = await svc.pull_changes(
            group_id=body.group_id,
            client_id=body.client_id,
            entity_types=body.entity_types,
        )
    except NotFoundError:
        raise HTTPException(404, "Sync state not found — register first")
    except ValueError as e:
        raise HTTPException(409, str(e))
    return SyncPullOut(**result)


@router.get("/conflicts", response_model=list[SyncConflictOut], summary="List conflicts")
async def list_conflicts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    sync_state_id: UUID | None = None,
) -> list[SyncConflictOut]:
    if sync_state_id is None:
        raise HTTPException(400, "sync_state_id is required")
    # Verify user owns this sync state by checking the state's user_id
    from sqlalchemy import select

    from openfmis.models.sync import SyncState

    svc = SyncService(db)
    result = await db.execute(select(SyncState).where(SyncState.id == sync_state_id))
    state = result.scalar_one_or_none()
    if state is None:
        raise HTTPException(404, "Sync state not found")
    if not current_user.is_superuser and state.user_id != current_user.id:
        raise HTTPException(403, "Access denied — sync state belongs to another user")

    items = await svc.list_conflicts(sync_state_id)
    return [SyncConflictOut.model_validate(c) for c in items]


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=SyncConflictOut,
    summary="Resolve conflict",
)
async def resolve_conflict(
    conflict_id: UUID,
    body: SyncConflictResolveRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SyncConflictOut:
    # Verify user owns the conflict's sync state
    from sqlalchemy import select

    from openfmis.models.sync import SyncConflict, SyncState

    result = await db.execute(
        select(SyncConflict, SyncState)
        .join(SyncState, SyncConflict.sync_state_id == SyncState.id)
        .where(SyncConflict.id == conflict_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(404, "Conflict not found")
    _, state = row
    if not current_user.is_superuser and state.user_id != current_user.id:
        raise HTTPException(403, "Access denied — conflict belongs to another user")

    svc = SyncService(db)
    try:
        conflict = await svc.resolve_conflict(
            conflict_id=conflict_id,
            resolution=body.resolution,
            resolved_data=body.resolved_data,
        )
    except NotFoundError:
        raise HTTPException(404, "Conflict not found")
    return SyncConflictOut.model_validate(conflict)
