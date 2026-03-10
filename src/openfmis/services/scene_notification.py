"""SceneNotificationService — alerts when new scenes match subscribed fields."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base

log = logging.getLogger(__name__)


# ── Notification model (lightweight — stored in same DB) ─────────────────────


class SceneNotification(Base):
    """A notification that a scene matches a user's subscribed fields."""

    __tablename__ = "scene_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str] = mapped_column(String(200), nullable=False)
    field_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fields.id", ondelete="CASCADE"), nullable=False
    )
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, default="new_scene")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    viewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<SceneNotification user={self.user_id} scene={self.scene_id}>"


class NotificationPreference(Base):
    """Per-user notification settings (email on/off, subscribed scene types, etc.)."""

    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scene_types: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ── Service ──────────────────────────────────────────────────────────────────


class SceneNotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Create notifications ─────────────────────────────────────────────

    async def notify_users_for_scene(
        self,
        scene_id: str,
        user_field_pairs: list[tuple[uuid.UUID, uuid.UUID]],
    ) -> list[SceneNotification]:
        """Create notifications for a list of (user_id, field_id) pairs."""
        notifications = []
        for user_id, field_id in user_field_pairs:
            # Skip duplicates
            existing = await self.db.execute(
                select(SceneNotification.id).where(
                    SceneNotification.user_id == user_id,
                    SceneNotification.scene_id == scene_id,
                    SceneNotification.field_id == field_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            notif = SceneNotification(
                user_id=user_id,
                scene_id=scene_id,
                field_id=field_id,
                message=f"New scene {scene_id} covers your field",
            )
            self.db.add(notif)
            notifications.append(notif)

        if notifications:
            await self.db.flush()
            for n in notifications:
                await self.db.refresh(n)
        return notifications

    # ── Query notifications ──────────────────────────────────────────────

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SceneNotification], int]:
        stmt = select(SceneNotification).where(
            SceneNotification.user_id == user_id,
            SceneNotification.visible.is_(True),
        )
        if unread_only:
            stmt = stmt.where(SceneNotification.viewed.is_(False))

        count_result = await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        total = count_result.scalar_one()

        result = await self.db.execute(
            stmt.order_by(SceneNotification.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def mark_viewed(self, notification_ids: list[uuid.UUID]) -> int:
        """Mark notifications as viewed. Returns count updated."""
        result = await self.db.execute(
            update(SceneNotification)
            .where(SceneNotification.id.in_(notification_ids))
            .values(viewed=True)
        )
        await self.db.flush()
        return result.rowcount

    async def set_visibility(self, notification_ids: list[uuid.UUID], visible: bool) -> int:
        result = await self.db.execute(
            update(SceneNotification)
            .where(SceneNotification.id.in_(notification_ids))
            .values(visible=visible)
        )
        await self.db.flush()
        return result.rowcount

    # ── Preferences ──────────────────────────────────────────────────────

    async def get_preferences(self, user_id: uuid.UUID) -> NotificationPreference | None:
        result = await self.db.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_preferences(
        self,
        user_id: uuid.UUID,
        email_enabled: bool | None = None,
        scene_types: dict | None = None,
        settings: dict | None = None,
    ) -> NotificationPreference:
        pref = await self.get_preferences(user_id)
        if pref is None:
            pref = NotificationPreference(user_id=user_id)
            self.db.add(pref)

        if email_enabled is not None:
            pref.email_enabled = email_enabled
        if scene_types is not None:
            pref.scene_types = scene_types
        if settings is not None:
            pref.settings = settings

        await self.db.flush()
        await self.db.refresh(pref)
        return pref

    async def clear_preferences(self, user_id: uuid.UUID) -> None:
        pref = await self.get_preferences(user_id)
        if pref:
            await self.db.delete(pref)
            await self.db.flush()
