"""Plugin SDK — Event bus re-export and scene event constants."""

from openfmis.core.events import event_bus

# Scene lifecycle events — canonical names
SCENE_INDEXED = "scene.indexed"
SCENE_MATCHED = "scene.matched"
ANALYSIS_COMPLETED = "analysis.completed"
ANALYSIS_APPROVED = "analysis.approved"

# Plugin lifecycle events
PLUGIN_REGISTERED = "plugin.registered"
PLUGIN_ACTIVATED = "plugin.activated"
PLUGIN_DEACTIVATED = "plugin.deactivated"

__all__ = [
    "event_bus",
    "SCENE_INDEXED",
    "SCENE_MATCHED",
    "ANALYSIS_COMPLETED",
    "ANALYSIS_APPROVED",
    "PLUGIN_REGISTERED",
    "PLUGIN_ACTIVATED",
    "PLUGIN_DEACTIVATED",
]
