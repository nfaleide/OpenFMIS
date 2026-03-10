"""Preference model — per-user settings by client/namespace."""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class Preference(Base, UUIDMixin, TimestampMixin):
    """User preference — replaces legacy `user_client_preferences`.

    Keyed by (user_id, namespace) where namespace is e.g. "web", "mobile", "notifications".
    """

    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("user_id", "namespace", name="uq_user_preference"),)
