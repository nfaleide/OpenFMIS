"""Photo CRUD endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.photo import PhotoCreate, PhotoList, PhotoRead, PhotoUpdate
from openfmis.services.photo import PhotoService

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("", response_model=PhotoList)
async def list_photos(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    object_type: str | None = None,
    object_id: UUID | None = None,
    field_event_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PhotoList:
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


@router.get("/{photo_id}", response_model=PhotoRead)
async def get_photo(
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    svc = PhotoService(db)
    photo = await svc.get_by_id(photo_id)
    return PhotoRead.model_validate(photo)


@router.post("", response_model=PhotoRead, status_code=201)
async def create_photo(
    body: PhotoCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    svc = PhotoService(db)
    photo = await svc.create_photo(body, uploaded_by=current_user.id)
    return PhotoRead.model_validate(photo)


@router.patch("/{photo_id}", response_model=PhotoRead)
async def update_photo(
    photo_id: UUID,
    body: PhotoUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PhotoRead:
    svc = PhotoService(db)
    photo = await svc.update_photo(photo_id, body)
    return PhotoRead.model_validate(photo)


@router.delete("/{photo_id}", status_code=204)
async def delete_photo(
    photo_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = PhotoService(db)
    await svc.soft_delete(photo_id)
