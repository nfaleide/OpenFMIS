"""Built-in plugin registrations — run once at startup via lifespan."""

from __future__ import annotations

import logging

from openfmis.core.events import event_bus
from openfmis.database import async_session_factory
from openfmis.schemas.plugin import PluginRegister
from openfmis.services.plugin import PluginAlreadyExistsError, PluginService

log = logging.getLogger(__name__)

BUILTIN_PLUGINS: list[dict] = [
    {
        "slug": "satshot",
        "name": "Satshot Imagery",
        "version": "1.0.0",
        "description": "AWS Sentinel-2 scene discovery, NDVI/NDWI analysis, and MVT tile serving.",
        "manifest": {
            "capabilities": [
                "scene_discovery",
                "image_extraction",
                "analysis_zones",
                "analysis_jobs",
                "tile_serving",
                "zone_editing",
                "saved_classifications",
                "auto_analysis",
                "scene_notifications",
                "vra_prescriptions",
                "imagery_export",
                "pdf_reports",
            ],
            "index_types": "dynamic",  # loaded from spectral_index_definitions table
            "stac_endpoint": "https://earth-search.aws.element84.com/v1",
            "collections": ["sentinel-2-l2a", "sentinel-1-grd", "landsat-c2-l2", "custom-upload"],
            "tile_layers": ["fields", "clu", "plss_townships", "plss_sections", "analysis_zones"],
            "credit_cost_per_scene": 10,
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
                # Already registered — update version/manifest in case it changed
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
