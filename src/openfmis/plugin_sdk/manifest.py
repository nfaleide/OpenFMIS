"""Plugin SDK — PluginManifest and supporting types.

Every plugin declares its capabilities, charge types, event subscriptions,
tile layers, and core version requirement via a PluginManifest.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChargeType(BaseModel):
    """A billable operation a plugin can perform."""

    operation: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_.]+$")
    description: str = Field("", max_length=500)


class EventSubscription(BaseModel):
    """An event the plugin wants to receive."""

    event: str = Field(..., min_length=1, max_length=200)
    handler_path: str = Field(..., min_length=1, max_length=500)


class PluginManifest(BaseModel):
    """Declarative manifest for an OpenFMIS plugin.

    This is the canonical description of what a plugin does and needs.
    Core uses it to auto-register hooks, validate billing, and enforce
    the privilege ceiling.
    """

    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=50)
    description: str = Field("", max_length=2000)

    capabilities: list[str] = Field(default_factory=list)
    charge_types: list[ChargeType] = Field(default_factory=list)
    subscribes_to: list[EventSubscription] = Field(default_factory=list)
    emits: list[str] = Field(default_factory=list)
    tile_layers: list[str] = Field(default_factory=list)
    dataset_types: list[str] = Field(default_factory=list)

    required_core_version: str = Field(">=0.1.0", max_length=50)
