"""PluginService — CRUD for the plugin registry + lifecycle events."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.core.events import event_bus
from openfmis.models.plugin import Plugin
from openfmis.schemas.plugin import PluginRegister, PluginUpdate


class PluginAlreadyExistsError(Exception):
    pass


class PluginNotFoundError(Exception):
    pass


class PluginService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Read ──────────────────────────────────────────────────────────────

    async def list_plugins(self, active_only: bool = False) -> list[Plugin]:
        stmt = select(Plugin).order_by(Plugin.slug)
        if active_only:
            stmt = stmt.where(Plugin.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_plugin(self, slug: str) -> Plugin | None:
        result = await self.db.execute(select(Plugin).where(Plugin.slug == slug))
        return result.scalar_one_or_none()

    async def get_plugin_by_id(self, plugin_id: int) -> Plugin | None:
        result = await self.db.execute(select(Plugin).where(Plugin.id == plugin_id))
        return result.scalar_one_or_none()

    # ── Write ─────────────────────────────────────────────────────────────

    async def register(self, data: PluginRegister) -> Plugin:
        """Create a new plugin registration. Raises PluginAlreadyExistsError if slug taken."""
        plugin = Plugin(
            slug=data.slug,
            name=data.name,
            version=data.version,
            description=data.description,
            manifest=data.manifest,
        )
        self.db.add(plugin)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise PluginAlreadyExistsError(data.slug)
        await self.db.refresh(plugin)
        await event_bus.emit(
            "plugin.registered", {"slug": plugin.slug, "manifest": plugin.manifest}
        )
        return plugin

    async def update(self, slug: str, data: PluginUpdate) -> Plugin:
        """Update an existing plugin. Raises PluginNotFoundError if not found."""
        plugin = await self.get_plugin(slug)
        if plugin is None:
            raise PluginNotFoundError(slug)

        changes = data.model_dump(exclude_none=True)
        for field, value in changes.items():
            setattr(plugin, field, value)
        await self.db.flush()
        await self.db.refresh(plugin)

        await event_bus.emit("plugin.updated", {"slug": plugin.slug, "manifest": plugin.manifest})
        return plugin

    async def set_active(self, slug: str, active: bool) -> Plugin:
        plugin = await self.get_plugin(slug)
        if plugin is None:
            raise PluginNotFoundError(slug)
        plugin.is_active = active
        await self.db.flush()
        await self.db.refresh(plugin)
        event_name = "plugin.activated" if active else "plugin.deactivated"
        await event_bus.emit(event_name, {"slug": plugin.slug, "manifest": plugin.manifest})
        return plugin

    async def unregister(self, slug: str) -> None:
        plugin = await self.get_plugin(slug)
        if plugin is None:
            raise PluginNotFoundError(slug)
        await self.db.delete(plugin)
        await self.db.flush()
        await event_bus.emit("plugin.unregistered", {"slug": slug, "manifest": {}})
