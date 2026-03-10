"""Photo model — geotagged field photos with cloud storage."""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Photo(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Geotagged photo — replaces legacy `geotagged_photos`.

    Original stored BYTEA (3 copies!). Modern: URL to cloud storage,
    thumbnails generated on demand.
    """

    __tablename__ = "photos"

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cloud storage URL (replaces BYTEA)
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)

    # Geolocation (optional — replaces legacy VARCHAR location)
    location: Mapped[None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )

    # Polymorphic association to any object (field, event, etc.)
    object_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # "field", "event", "entry"
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Optional link to a field event
    field_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("field_events.id"), nullable=True, index=True
    )


class EventPhoto(Base, TimestampMixin):
    """Junction: photos → field events. Replaces `geotagged_photos_fielddata_mapping`."""

    __tablename__ = "event_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("field_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
