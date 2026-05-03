"""Tests for the Plugin SDK — manifest, datasets, billing, hooks, events, ACL."""

import uuid

import pytest

from openfmis.models.core_dataset import CoreDataset
from openfmis.plugin_sdk.billing import get_balance, has_sufficient_balance, record_charge
from openfmis.plugin_sdk.datasets import (
    attach_dataset,
    delete_dataset,
    get_dataset,
    list_datasets_for_field,
)
from openfmis.plugin_sdk.events import (
    ANALYSIS_APPROVED,
    ANALYSIS_COMPLETED,
    SCENE_INDEXED,
    SCENE_MATCHED,
    event_bus,
)
from openfmis.plugin_sdk.hooks import (
    _clear_all_registries,
    get_cost_estimator,
    get_dataset_type,
    get_export_format,
    get_notification_provider,
    get_pdf_section,
    get_tile_layer,
    list_tile_layers,
    register_cost_estimator,
    register_dataset_type,
    register_export_format,
    register_notification_provider,
    register_pdf_section,
    register_plugin,
    register_tile_layer,
)
from openfmis.plugin_sdk.manifest import ChargeType, EventSubscription, PluginManifest
from openfmis.schemas.billing import CreditAdd
from openfmis.services.billing import CreditAccountingService, InsufficientCreditsError

pytestmark = pytest.mark.anyio


# ── Manifest validation ───────────��─────────────────────────────────────────


class TestPluginManifest:
    def test_valid_manifest(self):
        m = PluginManifest(
            slug="satshot",
            name="Satshot Imagery",
            version="1.0.0",
            description="Scene discovery + analysis",
            capabilities=["scene_discovery", "tile_serving"],
            charge_types=[
                ChargeType(operation="satshot.analysis", description="Per-scene NDVI"),
            ],
            subscribes_to=[
                EventSubscription(
                    event="scene.indexed",
                    handler_path="satshot.handlers.on_scene_indexed",
                ),
            ],
            emits=["scene.indexed", "analysis.completed"],
            tile_layers=["analysis_zones"],
            dataset_types=["analysis_result"],
            required_core_version=">=0.1.0",
        )
        assert m.slug == "satshot"
        assert len(m.charge_types) == 1
        assert m.charge_types[0].operation == "satshot.analysis"

    def test_invalid_slug_rejected(self):
        with pytest.raises(Exception):
            PluginManifest(slug="Bad Slug!", name="X", version="1.0")

    def test_minimal_manifest(self):
        m = PluginManifest(slug="minimal", name="Minimal", version="0.1.0")
        assert m.capabilities == []
        assert m.tile_layers == []

    def test_charge_type_validation(self):
        ct = ChargeType(operation="plugin.op", description="desc")
        assert ct.operation == "plugin.op"
        with pytest.raises(Exception):
            ChargeType(operation="INVALID OP!", description="bad")


# ── Dataset CRUD ───────��─────────────────���───────────────────────────────────


class TestDatasetService:
    async def test_attach_and_list(self, db_session, test_field):
        ds = await attach_dataset(
            db_session,
            plugin_slug="satshot",
            dataset_type="analysis_result",
            field_id=test_field.id,
            metadata={"ndvi_mean": 0.72},
            storage_url="s3://bucket/result.tif",
        )
        assert isinstance(ds, CoreDataset)
        assert ds.plugin_slug == "satshot"
        assert ds.extra_metadata["ndvi_mean"] == 0.72

        items = await list_datasets_for_field(db_session, test_field.id)
        assert len(items) == 1
        assert items[0].id == ds.id

    async def test_list_filtered_by_plugin(self, db_session, test_field):
        await attach_dataset(
            db_session,
            plugin_slug="satshot",
            dataset_type="scene_cache",
            field_id=test_field.id,
        )
        await attach_dataset(
            db_session,
            plugin_slug="sampling",
            dataset_type="sample_plan",
            field_id=test_field.id,
        )

        satshot_only = await list_datasets_for_field(
            db_session, test_field.id, plugin_slug="satshot"
        )
        assert len(satshot_only) == 1
        assert satshot_only[0].plugin_slug == "satshot"

    async def test_get_dataset(self, db_session, test_field):
        ds = await attach_dataset(
            db_session,
            plugin_slug="satshot",
            dataset_type="analysis_result",
            field_id=test_field.id,
        )
        fetched = await get_dataset(db_session, ds.id)
        assert fetched.id == ds.id

    async def test_delete_dataset(self, db_session, test_field):
        ds = await attach_dataset(
            db_session,
            plugin_slug="satshot",
            dataset_type="analysis_result",
            field_id=test_field.id,
        )
        await delete_dataset(db_session, ds.id)

        # Should not appear in list (soft-deleted)
        items = await list_datasets_for_field(db_session, test_field.id)
        assert len(items) == 0

    async def test_delete_nonexistent_raises(self, db_session):
        from openfmis.exceptions import NotFoundError

        with pytest.raises(NotFoundError):
            await delete_dataset(db_session, uuid.uuid4())


# ── Billing contract ─────────────────────────���───────────────────────────────


class TestBillingContract:
    async def test_get_balance_no_account(self, db_session):
        bal = await get_balance(db_session, "user", uuid.uuid4())
        assert bal == 0

    async def test_record_charge_and_balance(self, db_session, test_user):
        svc = CreditAccountingService(db_session)
        await svc.add_credits("user", test_user.id, CreditAdd(amount=100, note="seed"))
        await db_session.flush()

        bal = await get_balance(db_session, "user", test_user.id)
        assert bal == 100

        await record_charge(
            db_session,
            "user",
            test_user.id,
            operation="satshot.analysis",
            amount=10,
            note="analysis run",
        )
        await db_session.flush()

        bal = await get_balance(db_session, "user", test_user.id)
        assert bal == 90

    async def test_has_sufficient_balance(self, db_session, test_user):
        svc = CreditAccountingService(db_session)
        await svc.add_credits("user", test_user.id, CreditAdd(amount=50, note="seed"))
        await db_session.flush()

        assert await has_sufficient_balance(db_session, "user", test_user.id, 50)
        assert not await has_sufficient_balance(db_session, "user", test_user.id, 51)

    async def test_record_charge_insufficient(self, db_session, test_user):
        svc = CreditAccountingService(db_session)
        await svc.add_credits("user", test_user.id, CreditAdd(amount=5, note="seed"))
        await db_session.flush()

        with pytest.raises(InsufficientCreditsError):
            await record_charge(
                db_session,
                "user",
                test_user.id,
                operation="satshot.analysis",
                amount=10,
            )


# ── Hook registries ────────────────���───────────────────��─────────────────────


class TestHookRegistries:
    def setup_method(self):
        _clear_all_registries()

    def teardown_method(self):
        _clear_all_registries()

    def test_tile_layer_register_and_get(self):
        def my_sql(z, x, y):
            return f"SELECT 1 FROM t WHERE z={z}"

        register_tile_layer("custom_layer", "myplugin", my_sql)
        spec = get_tile_layer("custom_layer")
        assert spec is not None
        assert spec.plugin_slug == "myplugin"
        assert "SELECT 1" in spec.sql_builder(5, 0, 0)
        assert "custom_layer" in list_tile_layers()

    def test_dataset_type_register(self):
        register_dataset_type("satshot", "analysis_result")
        spec = get_dataset_type("analysis_result")
        assert spec is not None
        assert spec.plugin_slug == "satshot"

    def test_export_format_register(self):
        register_export_format("satshot", "geotiff", lambda: None)
        spec = get_export_format("geotiff")
        assert spec is not None
        assert spec.plugin_slug == "satshot"

    def test_notification_provider_register(self):
        register_notification_provider("satshot", "scene_alert", lambda: None)
        spec = get_notification_provider("scene_alert")
        assert spec is not None

    def test_pdf_section_register(self):
        register_pdf_section("satshot", "ndvi_map", lambda: None, sort_order=10)
        spec = get_pdf_section("ndvi_map")
        assert spec is not None
        assert spec.sort_order == 10

    def test_cost_estimator_register(self):
        register_cost_estimator("satshot", "satshot.analysis", lambda: 10)
        spec = get_cost_estimator("satshot.analysis")
        assert spec is not None

    def test_register_plugin_manifest(self):
        manifest = PluginManifest(
            slug="test-plugin",
            name="Test",
            version="1.0.0",
            tile_layers=["test_layer"],
            dataset_types=["test_dataset"],
            charge_types=[
                ChargeType(operation="test.op", description="test"),
            ],
        )
        register_plugin(manifest)

        assert "test_layer" in list_tile_layers()
        assert get_dataset_type("test_dataset") is not None

    def test_unknown_layer_returns_none(self):
        assert get_tile_layer("nonexistent") is None


# ── ACL delegation ───────────────��────────────────────���──────────────────────


class TestACLDelegation:
    async def test_check_permission_delegates(self, db_session, test_user):
        from openfmis.plugin_sdk.acl import check_permission

        # test_user's group has fielddata.read GRANT
        result = await check_permission(db_session, test_user, "fielddata.read", "fielddata")
        assert result is True

    async def test_check_permission_denied(self, db_session, test_user):
        from openfmis.plugin_sdk.acl import check_permission

        # test_user doesn't have view_financials
        result = await check_permission(db_session, test_user, "view_financials", "billing")
        assert result is False


# ── Scene events ─────────────────────────────────────────────────────────────


class TestSceneEvents:
    def test_event_constants(self):
        assert SCENE_INDEXED == "scene.indexed"
        assert SCENE_MATCHED == "scene.matched"
        assert ANALYSIS_COMPLETED == "analysis.completed"
        assert ANALYSIS_APPROVED == "analysis.approved"

    async def test_emit_scene_indexed(self):
        received = []

        async def handler(payload):
            received.append(payload)

        event_bus.subscribe("scene.indexed", handler)
        try:
            await event_bus.emit(
                "scene.indexed",
                {"scene_id": "S2A_123", "collection": "sentinel-2-l2a"},
            )
            assert len(received) == 1
            assert received[0]["scene_id"] == "S2A_123"
        finally:
            event_bus.unsubscribe("scene.indexed", handler)

    async def test_emit_analysis_completed(self):
        received = []

        async def handler(payload):
            received.append(payload)

        event_bus.subscribe("analysis.completed", handler)
        try:
            await event_bus.emit(
                "analysis.completed",
                {"job_id": "j-1", "field_id": "f-1"},
            )
            assert len(received) == 1
        finally:
            event_bus.unsubscribe("analysis.completed", handler)


# ── API endpoints ─────────────────────���─────────────────��────────────────────


class TestDatasetAPI:
    async def test_create_dataset(self, client, auth_headers, test_field):
        resp = await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "analysis_result",
                "field_id": str(test_field.id),
                "metadata": {"index": "ndvi"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["plugin_slug"] == "satshot"
        assert data["metadata"]["index"] == "ndvi"

    async def test_list_datasets(self, client, auth_headers, test_field):
        # Create two datasets
        await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "scene_cache",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "analysis_result",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/v1/datasets?field_id={test_field.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    async def test_get_dataset_detail(self, client, auth_headers, test_field):
        create_resp = await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "analysis_result",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )
        ds_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/datasets/{ds_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == ds_id

    async def test_delete_dataset(self, client, auth_headers, test_field):
        create_resp = await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "analysis_result",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )
        ds_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/datasets/{ds_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 204

        # Should be gone from list
        list_resp = await client.get(
            f"/api/v1/datasets?field_id={test_field.id}",
            headers=auth_headers,
        )
        assert list_resp.json()["total"] == 0

    async def test_list_datasets_filtered(self, client, auth_headers, test_field):
        await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "satshot",
                "dataset_type": "scene_cache",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/v1/datasets",
            json={
                "plugin_slug": "sampling",
                "dataset_type": "sample_plan",
                "field_id": str(test_field.id),
            },
            headers=auth_headers,
        )

        resp = await client.get(
            f"/api/v1/datasets?field_id={test_field.id}&plugin_slug=satshot",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["plugin_slug"] == "satshot"

    _clear_all_registries()
