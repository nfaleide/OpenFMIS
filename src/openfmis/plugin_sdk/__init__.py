"""OpenFMIS Plugin SDK — stable contract surface for all plugins.

Usage::

    from openfmis.plugin_sdk import PluginManifest, ChargeType, EventSubscription
    from openfmis.plugin_sdk import register_plugin, register_tile_layer
    from openfmis.plugin_sdk import event_bus, SCENE_INDEXED
    from openfmis.plugin_sdk import record_charge, get_balance
    from openfmis.plugin_sdk import check_permission
    from openfmis.plugin_sdk import attach_dataset, list_datasets_for_field
"""

# Manifest types
# ACL
from openfmis.plugin_sdk.acl import check_permission

# Billing
from openfmis.plugin_sdk.billing import (
    get_balance,
    has_sufficient_balance,
    record_charge,
)

# Datasets
from openfmis.plugin_sdk.datasets import (
    attach_dataset,
    delete_dataset,
    get_dataset,
    list_datasets_for_field,
)

# Events
from openfmis.plugin_sdk.events import (
    ANALYSIS_APPROVED,
    ANALYSIS_COMPLETED,
    SCENE_INDEXED,
    SCENE_MATCHED,
    event_bus,
)

# Hook registries
from openfmis.plugin_sdk.hooks import (
    register_charge_type,
    register_cost_estimator,
    register_dataset_type,
    register_export_format,
    register_notification_provider,
    register_pdf_section,
    register_plugin,
    register_tile_layer,
)
from openfmis.plugin_sdk.manifest import (
    ChargeType,
    EventSubscription,
    PluginManifest,
)

__all__ = [
    # Manifest
    "PluginManifest",
    "ChargeType",
    "EventSubscription",
    # Hooks
    "register_plugin",
    "register_tile_layer",
    "register_dataset_type",
    "register_export_format",
    "register_notification_provider",
    "register_pdf_section",
    "register_charge_type",
    "register_cost_estimator",
    # Events
    "event_bus",
    "SCENE_INDEXED",
    "SCENE_MATCHED",
    "ANALYSIS_COMPLETED",
    "ANALYSIS_APPROVED",
    # Billing
    "record_charge",
    "get_balance",
    "has_sufficient_balance",
    # ACL
    "check_permission",
    # Datasets
    "attach_dataset",
    "list_datasets_for_field",
    "get_dataset",
    "delete_dataset",
]
