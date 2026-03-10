"""PreferenceService — per-user settings by namespace."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.preference import Preference
from openfmis.schemas.preference import PreferenceUpsert


class PreferenceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, user_id: UUID, namespace: str) -> Preference:
        result = await self.db.execute(
            select(Preference).where(
                Preference.user_id == user_id,
                Preference.namespace == namespace,
            )
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            raise NotFoundError(f"Preference '{namespace}' not found")
        return pref

    async def list_for_user(self, user_id: UUID) -> list[Preference]:
        result = await self.db.execute(
            select(Preference).where(Preference.user_id == user_id).order_by(Preference.namespace)
        )
        return list(result.scalars().all())

    async def upsert(self, user_id: UUID, data: PreferenceUpsert) -> Preference:
        """Create or update a preference by (user_id, namespace)."""
        result = await self.db.execute(
            select(Preference).where(
                Preference.user_id == user_id,
                Preference.namespace == data.namespace,
            )
        )
        pref = result.scalar_one_or_none()

        if pref is None:
            pref = Preference(
                user_id=user_id,
                namespace=data.namespace,
                data=data.data,
            )
            self.db.add(pref)
        else:
            pref.data = data.data

        await self.db.flush()
        await self.db.refresh(pref)
        return pref

    async def delete(self, user_id: UUID, namespace: str) -> None:
        pref = await self.get(user_id, namespace)
        await self.db.delete(pref)
        await self.db.flush()
