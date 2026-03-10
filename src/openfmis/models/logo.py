"""Logo model — per-group branding for white-label reports."""

import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class Logo(Base, UUIDMixin, TimestampMixin):
    """Group logo — replaces legacy `customer_logos`.

    Original stored BYTEA. Modern: URL to cloud storage.
    """

    __tablename__ = "logos"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    storage_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # png, jpg, svg
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
