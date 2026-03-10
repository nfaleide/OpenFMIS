"""PhotoService — CRUD for geotagged photos."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.photo import EventPhoto, Photo
from openfmis.schemas.photo import PhotoCreate, PhotoUpdate


class PhotoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, photo_id: UUID) -> Photo:
        result = await self.db.execute(
            select(Photo).where(Photo.id == photo_id, Photo.deleted_at.is_(None))
        )
        photo = result.scalar_one_or_none()
        if photo is None:
            raise NotFoundError("Photo not found")
        return photo

    async def list_photos(
        self,
        object_type: str | None = None,
        object_id: UUID | None = None,
        field_event_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Photo], int]:
        query = select(Photo).where(Photo.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Photo).where(Photo.deleted_at.is_(None))

        if object_type is not None:
            query = query.where(Photo.object_type == object_type)
            count_query = count_query.where(Photo.object_type == object_type)

        if object_id is not None:
            query = query.where(Photo.object_id == object_id)
            count_query = count_query.where(Photo.object_id == object_id)

        if field_event_id is not None:
            query = query.where(Photo.field_event_id == field_event_id)
            count_query = count_query.where(Photo.field_event_id == field_event_id)

        query = query.order_by(Photo.created_at.desc()).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        photos = list(result.scalars().all())
        return photos, total

    async def create_photo(self, data: PhotoCreate, uploaded_by: UUID | None = None) -> Photo:
        photo = Photo(
            uploaded_by=uploaded_by,
            description=data.description,
            comments=data.comments,
            storage_url=data.storage_url,
            content_type=data.content_type,
            file_size_bytes=data.file_size_bytes,
            object_type=data.object_type,
            object_id=data.object_id,
            field_event_id=data.field_event_id,
        )

        # Set point geometry if lat/lon provided
        if data.latitude is not None and data.longitude is not None:
            photo.location = func.ST_SetSRID(func.ST_MakePoint(data.longitude, data.latitude), 4326)

        self.db.add(photo)
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def update_photo(self, photo_id: UUID, data: PhotoUpdate) -> Photo:
        photo = await self.get_by_id(photo_id)
        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(photo, attr, value)
        await self.db.flush()
        await self.db.refresh(photo)
        return photo

    async def soft_delete(self, photo_id: UUID) -> None:
        from datetime import UTC, datetime

        photo = await self.get_by_id(photo_id)
        photo.deleted_at = datetime.now(UTC)
        await self.db.flush()

    async def link_to_event(self, photo_id: UUID, event_id: UUID) -> EventPhoto:
        link = EventPhoto(photo_id=photo_id, event_id=event_id)
        self.db.add(link)
        await self.db.flush()
        return link
