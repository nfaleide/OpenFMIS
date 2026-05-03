"""Sync service tests — register, push, pull delta, conflict resolution."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.region import Region
from openfmis.services.sync import SyncService


async def _login(
    client: AsyncClient,
    username: str = "testuser",
    password: str = "testpassword123",
) -> str:
    resp = await client.post(
        "/api/v1/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Service-level tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_sync_client(db_session: AsyncSession, test_user, test_group):
    svc = SyncService(db_session)
    state = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="qgis-desktop-1",
    )
    assert state.client_id == "qgis-desktop-1"
    assert state.schema_version == 1
    assert state.pending_conflicts == 0
    assert state.last_sync_at is None


@pytest.mark.asyncio
async def test_register_idempotent(db_session: AsyncSession, test_user, test_group):
    svc = SyncService(db_session)
    s1 = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="qgis-1",
    )
    s2 = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="qgis-1",
    )
    assert s1.id == s2.id


@pytest.mark.asyncio
async def test_pull_empty_first_sync(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    """First pull (no last_sync_at) should return all group entities."""
    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="pull-test",
    )
    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="pull-test",
    )
    assert "changes" in result
    assert "sync_timestamp" in result
    assert isinstance(result["changes"], list)


@pytest.mark.asyncio
async def test_pull_returns_group_fields(
    db_session: AsyncSession,
    test_user,
    test_group,
    test_field,
):
    """Pull should include fields belonging to the group."""
    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="field-pull",
    )
    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="field-pull",
        entity_types=["field"],
    )
    field_changes = [c for c in result["changes"] if c["entity_type"] == "field"]
    assert len(field_changes) >= 1
    assert any(c["entity_id"] == str(test_field.id) for c in field_changes)
    assert field_changes[0]["action"] == "upsert"
    assert field_changes[0]["data"] is not None


@pytest.mark.asyncio
async def test_pull_returns_group_regions(
    db_session: AsyncSession,
    test_user,
    test_group,
    test_region,
):
    """Pull should include regions belonging to the group."""
    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="region-pull",
    )
    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="region-pull",
        entity_types=["region"],
    )
    region_changes = [c for c in result["changes"] if c["entity_type"] == "region"]
    assert len(region_changes) >= 1
    assert any(c["entity_id"] == str(test_region.id) for c in region_changes)


@pytest.mark.asyncio
async def test_pull_incremental(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    """After syncing with a future timestamp, pull returns empty."""
    svc = SyncService(db_session)
    state = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="incr-pull",
    )
    # Set last_sync_at to future so nothing is "new"
    state.last_sync_at = datetime.now(UTC) + timedelta(hours=1)
    await db_session.flush()

    result = await svc.pull_changes(group_id=test_group.id, client_id="incr-pull")
    assert result["changes"] == []


@pytest.mark.asyncio
async def test_pull_detects_new_entities(
    db_session: AsyncSession,
    test_user,
    test_group,
    test_region,
):
    """New entities created after last sync appear in pull."""
    svc = SyncService(db_session)
    state = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="detect-new",
    )
    # Set last_sync_at to well in the past so new entities are picked up
    state.last_sync_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    # Create a new region
    new_region = Region(
        id=uuid.uuid4(),
        name="New Sync Region",
        group_id=test_group.id,
    )
    db_session.add(new_region)
    await db_session.flush()

    # Pull should pick it up (updated_at >= last_sync_at)
    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="detect-new",
        entity_types=["region"],
    )
    new_ids = [c["entity_id"] for c in result["changes"]]
    assert str(new_region.id) in new_ids


@pytest.mark.asyncio
async def test_pull_soft_deleted_entities(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    """Soft-deleted entities appear with action='delete'."""
    svc = SyncService(db_session)
    state = await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="delete-test",
    )
    # Set last_sync_at to past
    state.last_sync_at = datetime.now(UTC) - timedelta(hours=1)
    await db_session.flush()

    # Create and then soft-delete a region
    r = Region(
        id=uuid.uuid4(),
        name="ToDelete",
        group_id=test_group.id,
    )
    db_session.add(r)
    await db_session.flush()

    r.deleted_at = datetime.now(UTC)
    await db_session.flush()

    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="delete-test",
        entity_types=["region"],
    )
    deleted = [c for c in result["changes"] if c["action"] == "delete"]
    assert len(deleted) >= 1
    assert deleted[0]["data"] is None


@pytest.mark.asyncio
async def test_push_and_conflict(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    """Push with server_data creates a conflict."""
    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="conflict-test",
    )
    result = await svc.push_changes(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="conflict-test",
        changes=[
            {
                "entity_type": "field",
                "entity_id": str(uuid.uuid4()),
                "updated_at": "2024-01-01T00:00:00Z",
                "server_data": {"name": "server version"},
                "data": {"name": "client version"},
            }
        ],
    )
    assert result["conflicts"] == 1
    assert len(result["conflict_ids"]) == 1


@pytest.mark.asyncio
async def test_resolve_conflict(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="resolve-test",
    )
    push_result = await svc.push_changes(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="resolve-test",
        changes=[
            {
                "entity_type": "region",
                "entity_id": str(uuid.uuid4()),
                "updated_at": "2024-01-01T00:00:00Z",
                "server_data": {"name": "server"},
                "data": {"name": "client"},
            }
        ],
    )
    cid = push_result["conflict_ids"][0]
    resolved = await svc.resolve_conflict(
        conflict_id=cid,
        resolution="server_wins",
    )
    assert resolved.resolved is True
    assert resolved.resolution == "server_wins"


@pytest.mark.asyncio
async def test_excludes_other_group(
    db_session: AsyncSession,
    test_user,
    test_group,
):
    """Pull should not include entities from other groups."""
    from openfmis.models.group import Group

    other_group = Group(id=uuid.uuid4(), name="OtherOrg")
    db_session.add(other_group)
    await db_session.flush()

    other_region = Region(
        id=uuid.uuid4(),
        name="Other Region",
        group_id=other_group.id,
    )
    db_session.add(other_region)
    await db_session.flush()

    svc = SyncService(db_session)
    await svc.register(
        user_id=test_user.id,
        group_id=test_group.id,
        client_id="isolation-test",
    )
    result = await svc.pull_changes(
        group_id=test_group.id,
        client_id="isolation-test",
        entity_types=["region"],
    )
    ids = [c["entity_id"] for c in result["changes"]]
    assert str(other_region.id) not in ids


# ── API-level tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_register(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/sync/register",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "client_id": "api-test-1",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["client_id"] == "api-test-1"


@pytest.mark.asyncio
async def test_api_push_pull_roundtrip(
    client: AsyncClient,
    test_user,
    test_group,
):
    token = await _login(client)
    # Register
    await client.post(
        "/api/v1/sync/register",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "client_id": "roundtrip",
        },
    )
    # Push
    resp = await client.post(
        "/api/v1/sync/push",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "client_id": "roundtrip",
            "changes": [
                {
                    "entity_type": "field",
                    "entity_id": str(uuid.uuid4()),
                    "data": {"name": "new field"},
                }
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["applied"] == 1

    # Pull
    resp = await client.post(
        "/api/v1/sync/pull",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "client_id": "roundtrip",
        },
    )
    assert resp.status_code == 200
    assert "changes" in resp.json()
    assert "sync_timestamp" in resp.json()
