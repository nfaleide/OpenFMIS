"""SubscriptionService — lifecycle management for recurring services."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.subscription import Subscription


class SubscriptionNotFoundError(Exception):
    pass


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def start(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        plugin_id: str,
        subscription_type: str,
        expires_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> Subscription:
        """Create a new subscription."""
        sub = Subscription(
            owner_type=owner_type,
            owner_id=owner_id,
            plugin_id=plugin_id,
            subscription_type=subscription_type,
            status="active",
            expires_at=expires_at,
            metadata_=metadata,
        )
        self.db.add(sub)
        await self.db.flush()
        await self.db.refresh(sub)
        return sub

    async def get(self, subscription_id: uuid.UUID) -> Subscription:
        result = await self.db.execute(
            select(Subscription).where(Subscription.id == subscription_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise SubscriptionNotFoundError(str(subscription_id))
        return sub

    async def renew(
        self,
        subscription_id: uuid.UUID,
        new_expires_at: datetime | None = None,
    ) -> Subscription:
        """Renew an active or expired subscription."""
        sub = await self.get(subscription_id)
        sub.status = "active"
        sub.renewed_at = datetime.now(UTC)
        if new_expires_at is not None:
            sub.expires_at = new_expires_at
        await self.db.flush()
        await self.db.refresh(sub)
        return sub

    async def cancel(
        self,
        subscription_id: uuid.UUID,
        reason: str | None = None,
    ) -> Subscription:
        """Cancel a subscription."""
        sub = await self.get(subscription_id)
        sub.status = "cancelled"
        sub.cancelled_at = datetime.now(UTC)
        sub.cancel_reason = reason
        await self.db.flush()
        await self.db.refresh(sub)
        return sub

    async def expire_due(self) -> int:
        """Expire all subscriptions past their expires_at. Returns count."""
        now = datetime.now(UTC)
        result = await self.db.execute(
            update(Subscription)
            .where(
                Subscription.status == "active",
                Subscription.expires_at.is_not(None),
                Subscription.expires_at <= now,
            )
            .values(status="expired")
        )
        await self.db.flush()
        return result.rowcount

    async def list_for_owner(
        self,
        owner_type: str,
        owner_id: uuid.UUID,
        status: str | None = None,
        plugin_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Subscription], int]:
        filters = [
            Subscription.owner_type == owner_type,
            Subscription.owner_id == owner_id,
        ]
        if status is not None:
            filters.append(Subscription.status == status)
        if plugin_id is not None:
            filters.append(Subscription.plugin_id == plugin_id)

        count_q = select(func.count()).select_from(Subscription).where(*filters)
        total = (await self.db.execute(count_q)).scalar_one()

        result = await self.db.execute(
            select(Subscription)
            .where(*filters)
            .order_by(Subscription.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total
