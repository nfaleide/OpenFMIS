"""Plugin SDK — Hook registries.

Plugins register capabilities (tile layers, dataset types, export formats,
notification providers, PDF sections, cost estimators) into in-memory
registries. Core services query these registries at runtime.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openfmis.plugin_sdk.manifest import PluginManifest

log = logging.getLogger(__name__)

# ── Tile layer registry ──────────────────────────────────────────────────────

SqlBuilder = Callable[[int, int, int], str]  # (z, x, y) → SQL string


@dataclass
class TileLayerSpec:
    """A plugin-provided tile layer."""

    layer_name: str
    plugin_slug: str
    sql_builder: SqlBuilder


_tile_registry: dict[str, TileLayerSpec] = {}


def register_tile_layer(layer_name: str, plugin_slug: str, sql_builder: SqlBuilder) -> None:
    """Register a plugin tile layer."""
    _tile_registry[layer_name] = TileLayerSpec(
        layer_name=layer_name, plugin_slug=plugin_slug, sql_builder=sql_builder
    )
    log.info("Registered tile layer '%s' from plugin '%s'", layer_name, plugin_slug)


def get_tile_layer(layer_name: str) -> TileLayerSpec | None:
    return _tile_registry.get(layer_name)


def list_tile_layers() -> list[str]:
    return list(_tile_registry.keys())


# ── Dataset type registry ────────────────────────────────────────────────────


@dataclass
class DatasetTypeSpec:
    type_name: str
    plugin_slug: str
    schema: Any = None  # Optional Pydantic model for metadata validation


_dataset_type_registry: dict[str, DatasetTypeSpec] = {}


def register_dataset_type(plugin_slug: str, type_name: str, schema: Any = None) -> None:
    _dataset_type_registry[type_name] = DatasetTypeSpec(
        type_name=type_name, plugin_slug=plugin_slug, schema=schema
    )
    log.info("Registered dataset type '%s' from plugin '%s'", type_name, plugin_slug)


def get_dataset_type(type_name: str) -> DatasetTypeSpec | None:
    return _dataset_type_registry.get(type_name)


def list_dataset_types() -> list[str]:
    return list(_dataset_type_registry.keys())


# ── Export format registry ───────────────────────────────────────────────────

ExportHandler = Callable[..., Any]


@dataclass
class ExportFormatSpec:
    format_name: str
    plugin_slug: str
    handler: ExportHandler


_export_format_registry: dict[str, ExportFormatSpec] = {}


def register_export_format(plugin_slug: str, format_name: str, handler: ExportHandler) -> None:
    _export_format_registry[format_name] = ExportFormatSpec(
        format_name=format_name, plugin_slug=plugin_slug, handler=handler
    )
    log.info("Registered export format '%s' from plugin '%s'", format_name, plugin_slug)


def get_export_format(format_name: str) -> ExportFormatSpec | None:
    return _export_format_registry.get(format_name)


def list_export_formats() -> list[str]:
    return list(_export_format_registry.keys())


# ── Notification provider registry ───────────────────────────────────────────

NotificationProvider = Callable[..., Any]


@dataclass
class NotificationProviderSpec:
    provider_name: str
    plugin_slug: str
    handler: NotificationProvider


_notification_provider_registry: dict[str, NotificationProviderSpec] = {}


def register_notification_provider(
    plugin_slug: str, provider_name: str, handler: NotificationProvider
) -> None:
    _notification_provider_registry[provider_name] = NotificationProviderSpec(
        provider_name=provider_name, plugin_slug=plugin_slug, handler=handler
    )
    log.info(
        "Registered notification provider '%s' from plugin '%s'",
        provider_name,
        plugin_slug,
    )


def get_notification_provider(provider_name: str) -> NotificationProviderSpec | None:
    return _notification_provider_registry.get(provider_name)


def list_notification_providers() -> list[str]:
    return list(_notification_provider_registry.keys())


# ── PDF section provider registry ────────────────────────────────────────────

PdfSectionProvider = Callable[..., Any]


@dataclass
class PdfSectionSpec:
    section_name: str
    plugin_slug: str
    handler: PdfSectionProvider
    sort_order: int = 0


_pdf_section_registry: dict[str, PdfSectionSpec] = {}


def register_pdf_section(
    plugin_slug: str,
    section_name: str,
    handler: PdfSectionProvider,
    sort_order: int = 0,
) -> None:
    _pdf_section_registry[section_name] = PdfSectionSpec(
        section_name=section_name,
        plugin_slug=plugin_slug,
        handler=handler,
        sort_order=sort_order,
    )
    log.info("Registered PDF section '%s' from plugin '%s'", section_name, plugin_slug)


def get_pdf_section(section_name: str) -> PdfSectionSpec | None:
    return _pdf_section_registry.get(section_name)


def list_pdf_sections() -> list[PdfSectionSpec]:
    return sorted(_pdf_section_registry.values(), key=lambda s: s.sort_order)


# ── Cost estimator registry ─────────────────────────────────────────────────

CostEstimator = Callable[..., Any]


@dataclass
class CostEstimatorSpec:
    operation: str
    plugin_slug: str
    estimator: CostEstimator


_cost_estimator_registry: dict[str, CostEstimatorSpec] = {}


def register_cost_estimator(plugin_slug: str, operation: str, estimator: CostEstimator) -> None:
    _cost_estimator_registry[operation] = CostEstimatorSpec(
        operation=operation, plugin_slug=plugin_slug, estimator=estimator
    )
    log.info("Registered cost estimator '%s' from plugin '%s'", operation, plugin_slug)


def get_cost_estimator(operation: str) -> CostEstimatorSpec | None:
    return _cost_estimator_registry.get(operation)


def list_cost_estimators() -> list[str]:
    return list(_cost_estimator_registry.keys())


# ── Charge type registry ────────────────────────────────────────────────────


@dataclass
class ChargeTypeSpec:
    operation: str
    plugin_slug: str
    description: str = ""


_charge_type_registry: dict[str, ChargeTypeSpec] = {}


def register_charge_type(plugin_slug: str, operation: str, description: str = "") -> None:
    _charge_type_registry[operation] = ChargeTypeSpec(
        operation=operation, plugin_slug=plugin_slug, description=description
    )
    log.info("Registered charge type '%s' from plugin '%s'", operation, plugin_slug)


def get_charge_type(operation: str) -> ChargeTypeSpec | None:
    return _charge_type_registry.get(operation)


def list_charge_types() -> list[ChargeTypeSpec]:
    return list(_charge_type_registry.values())


# ── Master plugin registration ──────────────────────��────────────────────────


def register_plugin(manifest: PluginManifest) -> None:
    """Auto-register all hooks declared in a plugin manifest.

    This registers tile layers, dataset types, and charge types from the
    manifest. Export formats, notification providers, PDF sections, and cost
    estimators require explicit registration with handlers.
    """
    for layer in manifest.tile_layers:
        # Tile layers from manifest are stubs — plugins must call
        # register_tile_layer() with an actual sql_builder separately.
        # We record the intent here so list_tile_layers() shows them.
        if layer not in _tile_registry:
            _tile_registry[layer] = TileLayerSpec(
                layer_name=layer,
                plugin_slug=manifest.slug,
                sql_builder=lambda z, x, y: "",  # placeholder
            )

    for dt in manifest.dataset_types:
        if dt not in _dataset_type_registry:
            register_dataset_type(manifest.slug, dt)

    for ct in manifest.charge_types:
        register_charge_type(manifest.slug, ct.operation, ct.description)

    log.info(
        "Plugin '%s' v%s registered: %d capabilities, %d tile layers, "
        "%d dataset types, %d charge types",
        manifest.slug,
        manifest.version,
        len(manifest.capabilities),
        len(manifest.tile_layers),
        len(manifest.dataset_types),
        len(manifest.charge_types),
    )


# ── Registry cleanup (for testing) ──────────────────────────────────────────


def _clear_all_registries() -> None:
    """Clear all hook registries. Only for use in tests."""
    _tile_registry.clear()
    _dataset_type_registry.clear()
    _export_format_registry.clear()
    _notification_provider_registry.clear()
    _pdf_section_registry.clear()
    _cost_estimator_registry.clear()
    _charge_type_registry.clear()
