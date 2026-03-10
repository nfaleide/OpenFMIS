"""Saved classification presets — user-defined zone class/color schemes."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class SavedClassification(Base):
    """A reusable classification preset (break points + color ramp)."""

    __tablename__ = "saved_classifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    index_type: Mapped[str] = mapped_column(String(20), nullable=False)
    num_classes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    breakpoints: Mapped[dict] = mapped_column(JSONB, nullable=False)
    colors: Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<SavedClassification {self.name} {self.index_type}>"
