"""Plugin registrations — built-in + external entry-point discovery.

External plugins declare an entry point in their pyproject.toml:

    [project.entry-points."openfmis.plugins"]
    my_plugin = "my_package.plugin:manifest"

The entry point must resolve to a PluginManifest instance or a callable
that returns one.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from openfmis.core.events import event_bus
from openfmis.database import async_session_factory
from openfmis.plugin_sdk.hooks import register_plugin
from openfmis.plugin_sdk.manifest import PluginManifest
from openfmis.schemas.plugin import PluginRegister
from openfmis.services.billing import PricingService
from openfmis.services.plugin import PluginAlreadyExistsError, PluginService

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "openfmis.plugins"

BUILTIN_PLUGINS: list[dict] = [
    {
        "slug": "sampling",
        "name": "Sampling",
        "version": "1.0.0",
        "description": (
            "Field sampling plan generation with random, grid, clustered, and W-pattern algorithms."
        ),
        "manifest": {
            "capabilities": [
                "sampling_plans",
                "point_generation",
                "field_collection",
                "zone_sampling",
                "auto_zone",
                "batch_sampling",
                "point_extraction",
            ],
            "algorithms": ["random", "grid", "clustered", "w"],
            "max_points_per_plan": 999,
        },
    },
]


async def register_builtin_plugins() -> None:
    """Upsert all built-in plugins at startup. Safe to call on every restart."""
    async with async_session_factory() as db:
        svc = PluginService(db)
        for spec in BUILTIN_PLUGINS:
            try:
                plugin = await svc.register(PluginRegister(**spec))
                await db.commit()
                log.info("Registered plugin: %s v%s", plugin.slug, plugin.version)
            except PluginAlreadyExistsError:
                from openfmis.schemas.plugin import PluginUpdate

                try:
                    await svc.update(
                        spec["slug"],
                        PluginUpdate(
                            version=spec["version"],
                            manifest=spec["manifest"],
                            description=spec.get("description"),
                        ),
                    )
                    await db.commit()
                    log.debug("Updated plugin: %s", spec["slug"])
                except Exception as exc:
                    log.warning("Could not update plugin %s: %s", spec["slug"], exc)
            except Exception as exc:
                log.warning("Could not register plugin %s: %s", spec["slug"], exc)


def discover_external_plugins() -> list[PluginManifest]:
    """Discover plugins via Python entry points (openfmis.plugins group).

    Each entry point should resolve to either:
    - A PluginManifest instance, or
    - A callable that returns a PluginManifest instance.
    """
    discovered: list[PluginManifest] = []
    eps = entry_points()
    plugin_eps = eps.select(group=ENTRY_POINT_GROUP) if hasattr(eps, "select") else []

    for ep in plugin_eps:
        try:
            obj = ep.load()
            if callable(obj) and not isinstance(obj, PluginManifest):
                obj = obj()
            if isinstance(obj, PluginManifest):
                discovered.append(obj)
                log.info("Discovered external plugin: %s v%s", obj.slug, obj.version)
            else:
                log.warning(
                    "Entry point '%s' did not resolve to a PluginManifest (got %s)",
                    ep.name,
                    type(obj).__name__,
                )
        except Exception as exc:
            log.warning("Failed to load plugin entry point '%s': %s", ep.name, exc)

    return discovered


async def register_external_plugins() -> None:
    """Discover and register all external plugins via entry points."""
    manifests = discover_external_plugins()
    if not manifests:
        log.debug("No external plugins discovered via entry points.")
        return

    async with async_session_factory() as db:
        svc = PluginService(db)
        for manifest in manifests:
            try:
                plugin = await svc.register(
                    PluginRegister(
                        slug=manifest.slug,
                        name=manifest.name,
                        version=manifest.version,
                        description=manifest.description,
                        manifest=manifest.model_dump(),
                    )
                )
                await db.commit()
                log.info("Registered external plugin: %s v%s", plugin.slug, plugin.version)
            except PluginAlreadyExistsError:
                from openfmis.schemas.plugin import PluginUpdate

                try:
                    await svc.update(
                        manifest.slug,
                        PluginUpdate(
                            version=manifest.version,
                            manifest=manifest.model_dump(),
                            description=manifest.description,
                        ),
                    )
                    await db.commit()
                    log.debug("Updated external plugin: %s", manifest.slug)
                except Exception as exc:
                    log.warning("Could not update plugin %s: %s", manifest.slug, exc)
            except Exception as exc:
                log.warning("Could not register plugin %s: %s", manifest.slug, exc)

            # Register hooks from the manifest
            register_plugin(manifest)

            # Sync declared charge types into price catalog
            if manifest.charge_types:
                pricing = PricingService(db)
                created = await pricing.sync_charge_types(manifest)
                if created:
                    await db.commit()
                    log.info(
                        "Synced %d new charge type(s) for plugin '%s'",
                        created,
                        manifest.slug,
                    )


# ── Event handlers wired to the global bus ────────────────────────────────────


@event_bus.on("plugin.registered")
async def _on_plugin_registered(payload: dict) -> None:
    log.info("Plugin registered: %s", payload.get("slug"))


@event_bus.on("plugin.activated")
async def _on_plugin_activated(payload: dict) -> None:
    log.info("Plugin activated: %s", payload.get("slug"))


@event_bus.on("plugin.deactivated")
async def _on_plugin_deactivated(payload: dict) -> None:
    log.info("Plugin deactivated: %s", payload.get("slug"))


# ── Sampling event handlers ─────────────────────────────────────────────────


@event_bus.on("sampling.plan.created")
async def _on_sampling_plan_created(payload: dict) -> None:
    log.info(
        "Sampling plan created: %s field=%s algo=%s",
        payload.get("plan_id"),
        payload.get("field_id"),
        payload.get("algorithm"),
    )


@event_bus.on("sampling.autozones.created")
async def _on_autozones_created(payload: dict) -> None:
    log.info(
        "Auto-zones created: field=%s job=%s count=%s",
        payload.get("field_id"),
        payload.get("job_id"),
        payload.get("zone_count"),
    )
