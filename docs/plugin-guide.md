# Plugin Guide

This guide covers building plugins for OpenFMIS. Plugins extend the platform with custom tile layers, dataset types, export formats, billing operations, event handlers, and more — without modifying core code.

## Overview

A plugin consists of:
1. A **manifest** declaring capabilities
2. **Hook registrations** for tile layers, datasets, exports, etc.
3. **Event handlers** reacting to system events
4. **Service logic** for domain-specific operations

## Plugin Manifest

Every plugin starts with a `PluginManifest`:

```python
from openfmis.plugin_sdk import PluginManifest, ChargeType, EventSubscription

manifest = PluginManifest(
    slug="my-plugin",                    # lowercase, hyphens/underscores only
    name="My Plugin",
    version="1.0.0",
    description="What this plugin does",
    capabilities=["scene_discovery", "tile_serving"],
    charge_types=[
        ChargeType(
            operation="my-plugin.analysis",  # lowercase, dots/underscores
            description="Per-field analysis run",
        ),
    ],
    subscribes_to=[
        EventSubscription(
            event="scene.indexed",
            handler_path="my_plugin.handlers.on_scene_indexed",
        ),
    ],
    emits=["analysis.completed"],
    tile_layers=["my_custom_layer"],
    dataset_types=["analysis_result"],
    required_core_version=">=0.1.0",
)
```

### Manifest Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slug` | str | Yes | Unique identifier (pattern: `^[a-z0-9_-]+$`) |
| `name` | str | Yes | Display name |
| `version` | str | Yes | Semantic version |
| `description` | str | No | Up to 2000 chars |
| `capabilities` | list[str] | No | Capability tags |
| `charge_types` | list[ChargeType] | No | Billable operations |
| `subscribes_to` | list[EventSubscription] | No | Event subscriptions |
| `emits` | list[str] | No | Events this plugin can emit |
| `tile_layers` | list[str] | No | Tile layer names to register |
| `dataset_types` | list[str] | No | Dataset type names to register |
| `required_core_version` | str | No | Version constraint (default `>=0.1.0`) |

## Registration

Register your plugin at startup using `register_plugin()`:

```python
from openfmis.plugin_sdk import register_plugin

register_plugin(manifest)
```

This auto-registers:
- Tile layers listed in `manifest.tile_layers` (stub SQL builders — override with `register_tile_layer`)
- Dataset types listed in `manifest.dataset_types`
- Charge types listed in `manifest.charge_types`

## Hook Registries

### Tile Layers

Serve custom PostGIS data as Mapbox Vector Tiles:

```python
from openfmis.plugin_sdk import register_tile_layer

def analysis_zones_sql(z: int, x: int, y: int) -> str:
    envelope = "ST_TileEnvelope(:z, :x, :y)"
    return f"""
    WITH tile AS (
        SELECT
            az.id::text AS id,
            az.zone_name,
            ST_AsMVTGeom(
                ST_Transform(az.geometry, 3857),
                {envelope}, 4096, 64, true
            ) AS geom
        FROM analysis_zones az
        WHERE az.geometry IS NOT NULL
            AND ST_Intersects(az.geometry, ST_Transform({envelope}, 4326))
    )
    SELECT ST_AsMVT(tile, 'analysis_zones', 4096, 'geom') FROM tile
    """

register_tile_layer("analysis_zones", "my-plugin", analysis_zones_sql)
```

Tiles are served at `GET /api/v1/tiles/{layer}/{z}/{x}/{y}.mvt`.

### Dataset Types

Register custom dataset types that can be attached to fields:

```python
from openfmis.plugin_sdk import register_dataset_type

register_dataset_type("my-plugin", "analysis_result")
```

### Export Formats

Add custom export formats:

```python
from openfmis.plugin_sdk import register_export_format

async def export_my_format(fields, options):
    # Generate export bytes
    return b"..."

register_export_format("my-plugin", "my-format", export_my_format)
```

### Notification Providers

Custom notification delivery:

```python
from openfmis.plugin_sdk import register_notification_provider

async def send_alert(user_id, message, metadata):
    # Send via SMS, Slack, etc.
    pass

register_notification_provider("my-plugin", "sms_alert", send_alert)
```

### PDF Sections

Add sections to generated PDF reports:

```python
from openfmis.plugin_sdk import register_pdf_section

async def render_ndvi_map(field_id, job_id):
    return "<div>NDVI map HTML</div>"

register_pdf_section("my-plugin", "ndvi_map", render_ndvi_map, sort_order=10)
```

### Cost Estimators

Dynamic pricing for operations:

```python
from openfmis.plugin_sdk import register_cost_estimator

def estimate_analysis_cost(field_acres, options):
    return max(10, int(field_acres * 0.5))

register_cost_estimator("my-plugin", "my-plugin.analysis", estimate_analysis_cost)
```

### Charge Types

Register billable operations (also done via manifest):

```python
from openfmis.plugin_sdk import register_charge_type

register_charge_type("my-plugin", "my-plugin.analysis", "Per-field analysis")
```

## Event Bus

### Subscribing to Events

```python
from openfmis.plugin_sdk import event_bus

async def on_scene_indexed(payload: dict):
    scene_id = payload["scene_id"]
    collection = payload["collection"]
    # Process the new scene...

event_bus.subscribe("scene.indexed", on_scene_indexed)
```

### Emitting Events

```python
await event_bus.emit("analysis.completed", {
    "job_id": "j-123",
    "field_id": "f-456",
    "status": "success",
})
```

### Built-in Events

| Event | Payload | Description |
|-------|---------|-------------|
| `scene.indexed` | `{scene_id, collection}` | New satellite scene available |
| `scene.matched` | `{scene_id, field_id}` | Scene matched to a field |
| `analysis.completed` | `{job_id, field_id, status}` | Analysis job finished |
| `analysis.approved` | `{job_id, field_id}` | Analysis result approved by user |
| `plugin.registered` | `{slug, name, version}` | Plugin registered |
| `plugin.activated` | `{slug}` | Plugin activated |
| `plugin.deactivated` | `{slug}` | Plugin deactivated |

## Dataset Attachment

Attach plugin-specific data to fields:

```python
from openfmis.plugin_sdk import attach_dataset, get_dataset, list_datasets_for_field, delete_dataset

# Create
ds = await attach_dataset(
    db_session,
    plugin_slug="my-plugin",
    dataset_type="analysis_result",
    field_id=field_id,
    metadata={"ndvi_mean": 0.72, "cloud_cover": 5.2},
    storage_url="s3://bucket/results/field-123.tif",
)

# Read
ds = await get_dataset(db_session, dataset_id)

# List (optionally filtered by plugin or type)
datasets = await list_datasets_for_field(
    db_session, field_id,
    plugin_slug="my-plugin",
    dataset_type="analysis_result",
)

# Delete (soft)
await delete_dataset(db_session, dataset_id)
```

## Billing

### Charging Credits

```python
from openfmis.plugin_sdk import record_charge, get_balance, has_sufficient_balance

# Check before charging
if not await has_sufficient_balance(db, "user", user_id, 10):
    raise ValueError("Insufficient credits")

# Charge (raises InsufficientCreditsError if balance too low)
await record_charge(
    db_session,
    owner_type="user",
    owner_id=user_id,
    operation="my-plugin.analysis",
    amount=10,
    note="Analysis of Field North-40",
)

# Check balance
balance = await get_balance(db_session, "user", user_id)
```

### Price Catalog

Charge types declared in the manifest are auto-registered in the price catalog. Admins set prices via `PUT /api/v1/billing/prices/{operation}`.

## ACL Delegation

Check permissions from plugin code:

```python
from openfmis.plugin_sdk import check_permission

allowed = await check_permission(
    db_session,
    user=current_user,
    permission="fielddata.read",
    resource_type="fielddata",
)
if not allowed:
    raise PermissionError("Access denied")
```

## Full Plugin API Surface

```python
from openfmis.plugin_sdk import (
    # Manifest
    PluginManifest, ChargeType, EventSubscription,
    # Registration
    register_plugin,
    # Hooks
    register_tile_layer, register_dataset_type,
    register_export_format, register_notification_provider,
    register_pdf_section, register_charge_type, register_cost_estimator,
    # Events
    event_bus,
    SCENE_INDEXED, SCENE_MATCHED, ANALYSIS_COMPLETED, ANALYSIS_APPROVED,
    # Billing
    record_charge, get_balance, has_sufficient_balance,
    # ACL
    check_permission,
    # Datasets
    attach_dataset, list_datasets_for_field, get_dataset, delete_dataset,
)
```

## Example: Minimal Plugin

```python
"""Example plugin that adds a tile layer and reacts to scene events."""

from openfmis.plugin_sdk import (
    PluginManifest, ChargeType,
    register_plugin, register_tile_layer,
    event_bus, record_charge,
)

manifest = PluginManifest(
    slug="example-plugin",
    name="Example Plugin",
    version="0.1.0",
    description="Demonstrates the plugin SDK",
    charge_types=[
        ChargeType(operation="example.process", description="Per-field processing"),
    ],
    tile_layers=["example_layer"],
)

def example_sql(z, x, y):
    envelope = "ST_TileEnvelope(:z, :x, :y)"
    return f"""
    WITH tile AS (
        SELECT id::text, name,
            ST_AsMVTGeom(ST_Transform(geom, 3857), {envelope}, 4096, 64, true) AS geom
        FROM my_table
        WHERE ST_Intersects(geom, ST_Transform({envelope}, 4326))
    )
    SELECT ST_AsMVT(tile, 'example_layer', 4096, 'geom') FROM tile
    """

async def on_scene_indexed(payload):
    print(f"New scene: {payload['scene_id']}")

def register():
    register_plugin(manifest)
    register_tile_layer("example_layer", "example-plugin", example_sql)
    event_bus.subscribe("scene.indexed", on_scene_indexed)
```
