"""Photo CRUD endpoints with ACL enforcement inherited from parent field."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.exceptions import AuthorizationError
from openfmis.models.user import User
from openfmis.schemas.photo import PhotoCreate, PhotoList, PhotoRead, PhotoUpdate
from openfmis.services.acl import ACLService
from openfmis.services.photo import PhotoService

router = APIRouter(prefix="/photos", tags=["photos"])


async def _check_field_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: UUID | None = None,
) -> None:
    """Check a fields.* permission (photos inherit from parent field)."""
    acl = ACLService(db)
    allowed = await acl.check_permission(user, permission, "fields", resource_id)
    if not allowed:
        raise AuthorizationError(f"Permission '{permission}' denied on 'fields'")


async def _resolve_photo_field_id(db: AsyncSession, photo_id: UUID) -> UUID | None:
    """Resolve the parent field ID for a photo (via object_type='field')."""
    from openfmis.models.photo import Photo

    result = await db.execute(
        select(Photo.object_type, Photo.object_id).where(
            Photo.id == photo_id, Photo.deleted_at.is_(None)
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    if row.object_type == "field":
        return row.object_id
    return None


@router.get("", response_model=PhotoList, summary="List photos")
async def list_photos(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    object_type: str | None = None,
    object_id: UUID | None = None,
    field_event_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PhotoList:
    acl = ACLService(db)
    if not current_user.is_superuser:
        allowed = await acl.check_permission(current_user, "fields.read", "fields")
        if not allowed:
            return PhotoList(items=[], total=0)

    svc = PhotoService(db)
    photos, total = await svc.list_photos(
        object_type=object_type,
        object_id=object_id,
        field_event_id=field_event_id,
        offset=offset,
        limit=limit,
    )
    return PhotoList(
        items=[PhotoRead.model_validate(p) for p in photos],
        total=total,
    )


@router.get("/{photo_id}", response_model=PhotoRead, summary="Get photo")
async def get_photo(
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    field_id = await _resolve_photo_field_id(db, photo_id)
    await _check_field_permission(db, current_user, "fields.read", field_id)
    svc = PhotoService(db)
    photo = await svc.get_by_id(photo_id)
    return PhotoRead.model_validate(photo)


@router.post("", response_model=PhotoRead, status_code=201, summary="Create photo")
async def create_photo(
    body: PhotoCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    # Check per-field ACL if photo is being attached to a field
    field_id = body.object_id if body.object_type == "field" else None
    await _check_field_permission(db, current_user, "fields.modify", field_id)
    svc = PhotoService(db)
    photo = await svc.create_photo(body, uploaded_by=current_user.id)
    return PhotoRead.model_validate(photo)


@router.patch("/{photo_id}", response_model=PhotoRead, summary="Update photo")
async def update_photo(
    photo_id: UUID,
    body: PhotoUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    field_id = await _resolve_photo_field_id(db, photo_id)
    await _check_field_permission(db, current_user, "fields.modify", field_id)
    svc = PhotoService(db)
    photo = await svc.update_photo(photo_id, body)
    return PhotoRead.model_validate(photo)


@router.delete("/{photo_id}", status_code=204, summary="Delete photo")
async def delete_photo(
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    field_id = await _resolve_photo_field_id(db, photo_id)
    await _check_field_permission(db, current_user, "fields.modify", field_id)
    svc = PhotoService(db)
    await svc.soft_delete(photo_id)
