"""Token blacklist — tracks revoked JWTs (replaces legacy loginsessions table)."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from openfmis.models.base import Base, UUIDMixin


class TokenBlacklist(Base, UUIDMixin):
    __tablename__ = "token_blacklist"

    jti: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<TokenBlacklist jti={self.jti[:8]}...>"
