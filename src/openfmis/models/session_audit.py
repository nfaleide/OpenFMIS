"""Session audit log model -- tracks login/logout events."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base


class SessionAudit(Base):
    __tablename__ = "session_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "login", "logout", "token_refresh", "login_failed"
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    jti: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # JWT ID for correlating login/logout
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_session_audit_user", "user_id"),
        Index("idx_session_audit_user_created", "user_id", "created_at"),
        Index("idx_session_audit_event_type", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<SessionAudit {self.event_type} user={self.user_id}>"
