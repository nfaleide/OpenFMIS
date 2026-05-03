"""ExportLink model — shareable download links with SHA-256 hash + expiry."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class ExportLink(Base):
    __tablename__ = "export_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_downloads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False, server_default="'export'")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_export_links_hash", "hash"),
        Index("idx_export_links_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<ExportLink {self.hash[:12]}… format={self.format}>"
