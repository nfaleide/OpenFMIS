"""Privilege models — JSONB permissions with tri-state GRANT/ALLOW/DENY.

Replaces legacy boolean columns in user_privileges and
tri-state VARCHAR columns in group_privileges.
"""

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, TimestampMixin, UUIDMixin


class PermissionState(StrEnum):
    GRANT = "GRANT"
    ALLOW = "ALLOW"
    DENY = "DENY"


class UserPrivilege(Base, UUIDMixin, TimestampMixin):
    """Per-user permission grants.

    permissions column example:
    {
        "fields.read": "GRANT",
        "fields.write": "ALLOW",
        "admin.users": "DENY"
    }
    """

    __tablename__ = "user_privileges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user = relationship("User", back_populates="privileges")


class GroupPrivilege(Base, UUIDMixin, TimestampMixin):
    """Per-group permission grants — inherited by all group members."""

    __tablename__ = "group_privileges"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    group = relationship("Group", back_populates="privileges")
