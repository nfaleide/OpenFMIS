"""LogoService — per-group branding logos."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.logo import Logo
from openfmis.schemas.logo import LogoUpsert


class LogoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_group(self, group_id: UUID) -> Logo:
        result = await self.db.execute(select(Logo).where(Logo.group_id == group_id))
        logo = result.scalar_one_or_none()
        if logo is None:
            raise NotFoundError("Logo not found for group")
        return logo

    async def upsert(self, data: LogoUpsert) -> Logo:
        """Create or update the logo for a group (one per group)."""
        result = await self.db.execute(select(Logo).where(Logo.group_id == data.group_id))
        logo = result.scalar_one_or_none()

        if logo is None:
            logo = Logo(
                group_id=data.group_id,
                storage_url=data.storage_url,
                file_type=data.file_type,
                width=data.width,
                height=data.height,
            )
            self.db.add(logo)
        else:
            logo.storage_url = data.storage_url
            logo.file_type = data.file_type
            logo.width = data.width
            logo.height = data.height

        await self.db.flush()
        await self.db.refresh(logo)
        return logo

    async def delete(self, group_id: UUID) -> None:
        logo = await self.get_by_group(group_id)
        await self.db.delete(logo)
        await self.db.flush()
