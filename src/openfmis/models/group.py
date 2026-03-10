"""Group model — self-referential tree via parent_id (replaces legacy dgroups)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from openfmis.models.privilege import GroupPrivilege
    from openfmis.models.user import User


class Group(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "groups"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Self-referential hierarchy
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id"),
        nullable=True,
        index=True,
    )

    # Extensible settings per group
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)

    # Relationships
    parent: Mapped[Group | None] = relationship(
        back_populates="children", remote_side="Group.id", lazy="selectin"
    )
    children: Mapped[list[Group]] = relationship(back_populates="parent", lazy="selectin")
    users: Mapped[list[User]] = relationship(back_populates="group", lazy="selectin")
    privileges: Mapped[list[GroupPrivilege]] = relationship(
        back_populates="group", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Group {self.name}>"
