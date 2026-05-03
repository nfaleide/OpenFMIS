"""Session audit service -- records login/logout/failed events."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.session_audit import SessionAudit


class SessionAuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(
        self,
        user_id: uuid.UUID,
        event_type: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        jti: str | None = None,
    ) -> SessionAudit:
        entry = SessionAudit(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            jti=jti,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        event_type: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SessionAudit], int]:
        filters = [SessionAudit.user_id == user_id]
        if event_type is not None:
            filters.append(SessionAudit.event_type == event_type)

        count_result = await self.db.execute(
            select(func.count()).select_from(SessionAudit).where(*filters)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(SessionAudit)
            .where(*filters)
            .order_by(SessionAudit.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
