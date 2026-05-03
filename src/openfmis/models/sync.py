"""Sync models — bidirectional sync state and conflict resolution."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class SyncState(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sync_state"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    pending_conflicts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "group_id", "client_id", name="uq_sync_state_user_group_client"
        ),
    )

    # Relationships
    user = relationship("User", lazy="selectin")
    group = relationship("Group", lazy="selectin")
    conflicts: Mapped[list["SyncConflict"]] = relationship(
        back_populates="sync_state",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SyncConflict(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sync_conflicts"

    sync_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sync_state.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    server_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    client_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    sync_state: Mapped["SyncState"] = relationship(back_populates="conflicts")
