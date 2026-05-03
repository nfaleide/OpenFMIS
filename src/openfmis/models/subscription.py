"""Generic subscription model — lifecycle primitives for recurring services.

Used by plugins for auto-analysis subscriptions, data feeds, farm forks, etc.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class Subscription(Base):
    """A generic subscription tracking recurring service usage."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "user" | "group"
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    plugin_id: Mapped[str] = mapped_column(String(100), nullable=False)
    subscription_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'cancelled', 'suspended')",
            name="ck_subscription_status",
        ),
        CheckConstraint(
            "owner_type IN ('user', 'group')",
            name="ck_subscription_owner_type",
        ),
        Index("idx_subscriptions_owner", "owner_type", "owner_id"),
        Index("idx_subscriptions_plugin", "plugin_id"),
        Index("idx_subscriptions_status", "status"),
        Index("idx_subscriptions_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Subscription {self.subscription_type} "
            f"{self.owner_type}:{self.owner_id} {self.status}>"
        )
