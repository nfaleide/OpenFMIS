"""External plugin loader tests — entry-point discovery + manifest registration."""

from unittest.mock import MagicMock, patch

import pytest

from openfmis.core.plugin_registry import discover_external_plugins
from openfmis.plugin_sdk.hooks import _clear_all_registries, list_tile_layers, register_plugin
from openfmis.plugin_sdk.manifest import ChargeType, EventSubscription, PluginManifest


@pytest.fixture(autouse=True)
def clean_registries():
    """Clean hook registries before and after each test."""
    _clear_all_registries()
    yield
    _clear_all_registries()


def test_discover_no_plugins():
    """When no entry points exist, returns empty list."""
    with patch("openfmis.core.plugin_registry.entry_points") as mock_eps:
        mock_result = MagicMock()
        mock_result.select.return_value = []
        mock_eps.return_value = mock_result
        result = discover_external_plugins()
        assert result == []


def test_discover_manifest_instance():
    """Entry point resolving to a PluginManifest instance is discovered."""
    manifest = PluginManifest(
        slug="test-ext",
        name="Test External",
        version="0.1.0",
    )

    mock_ep = MagicMock()
    mock_ep.name = "test-ext"
    mock_ep.load.return_value = manifest

    with patch("openfmis.core.plugin_registry.entry_points") as mock_eps:
        mock_result = MagicMock()
        mock_result.select.return_value = [mock_ep]
        mock_eps.return_value = mock_result
        result = discover_external_plugins()

    assert len(result) == 1
    assert result[0].slug == "test-ext"


def test_discover_callable_factory():
    """Entry point resolving to a callable that returns a manifest is discovered."""
    manifest = PluginManifest(
        slug="factory-plugin",
        name="Factory Plugin",
        version="2.0.0",
        capabilities=["analysis"],
    )

    def factory():
        return manifest

    mock_ep = MagicMock()
    mock_ep.name = "factory-plugin"
    mock_ep.load.return_value = factory

    with patch("openfmis.core.plugin_registry.entry_points") as mock_eps:
        mock_result = MagicMock()
        mock_result.select.return_value = [mock_ep]
        mock_eps.return_value = mock_result
        result = discover_external_plugins()

    assert len(result) == 1
    assert result[0].slug == "factory-plugin"
    assert "analysis" in result[0].capabilities


def test_discover_invalid_entry_point_skipped():
    """Entry point that returns wrong type is logged and skipped."""
    mock_ep = MagicMock()
    mock_ep.name = "bad-plugin"
    mock_ep.load.return_value = "not a manifest"

    with patch("openfmis.core.plugin_registry.entry_points") as mock_eps:
        mock_result = MagicMock()
        mock_result.select.return_value = [mock_ep]
        mock_eps.return_value = mock_result
        result = discover_external_plugins()

    assert result == []


def test_discover_exception_in_load_skipped():
    """Entry point that raises on load is logged and skipped."""
    mock_ep = MagicMock()
    mock_ep.name = "crash-plugin"
    mock_ep.load.side_effect = ImportError("missing dependency")

    with patch("openfmis.core.plugin_registry.entry_points") as mock_eps:
        mock_result = MagicMock()
        mock_result.select.return_value = [mock_ep]
        mock_eps.return_value = mock_result
        result = discover_external_plugins()

    assert result == []


def test_register_plugin_wires_tile_layers():
    """register_plugin() from a manifest registers declared tile layers."""
    manifest = PluginManifest(
        slug="tile-test",
        name="Tile Test Plugin",
        version="1.0.0",
        tile_layers=["my_custom_layer"],
    )
    register_plugin(manifest)
    assert "my_custom_layer" in list_tile_layers()


def test_manifest_with_full_features():
    """A fully-featured manifest validates correctly."""
    manifest = PluginManifest(
        slug="full-plugin",
        name="Full Feature Plugin",
        version="3.0.0",
        description="A plugin with all features",
        capabilities=["scene_discovery", "analysis"],
        charge_types=[
            ChargeType(operation="full.analyze", description="Per-scene analysis"),
        ],
        subscribes_to=[
            EventSubscription(
                event="scene.indexed",
                handler_path="full_plugin.handlers.on_indexed",
            ),
        ],
        emits=["analysis.completed"],
        tile_layers=["full_zones"],
        dataset_types=["analysis_result"],
        required_core_version=">=0.1.0",
    )
    assert manifest.slug == "full-plugin"
    assert len(manifest.charge_types) == 1
    assert manifest.charge_types[0].operation == "full.analyze"


def test_manifest_validation_rejects_invalid_slug():
    """Manifest rejects slugs with uppercase or special chars."""
    with pytest.raises(Exception):
        PluginManifest(slug="BAD SLUG!", name="Bad", version="1.0.0")
