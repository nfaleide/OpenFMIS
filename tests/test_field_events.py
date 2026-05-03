"""FieldEvent tests — CRUD, versioning, sub-entries, all 9 event types, ACL."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.field_event import EventType
from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege, PermissionState
from openfmis.models.region import Region
from openfmis.models.user import User
from openfmis.schemas.field_event import (
    FieldEventCreate,
    FieldEventEntryCreate,
)
from openfmis.security.password import hash_password
from openfmis.services.field_event import FieldEventService


async def _login(
    client: AsyncClient, username: str = "testuser", password: str = "testpassword123"
) -> str:
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="EventCo")
    db_session.add(group)
    await db_session.flush()
    field_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": "GRANT",
            "fields.create": "GRANT",
            "fields.modify": "GRANT",
            "fields.delete": "GRANT",
        },
    )
    db_session.add(field_priv)
    fielddata_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="fielddata",
        resource_id=None,
        permissions={
            "fielddata.read": "GRANT",
            "fielddata.append": "GRANT",
            "fielddata.modify": "GRANT",
        },
    )
    db_session.add(fielddata_priv)
    await db_session.flush()
    return group


@pytest.fixture
async def test_region(db_session: AsyncSession, test_group: Group) -> Region:
    region = Region(id=uuid.uuid4(), name="EventRegion", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()
    return region


@pytest.fixture
async def test_field(db_session: AsyncSession, test_group: Group, test_region: Region) -> Field:
    field = Field(
        id=uuid.uuid4(),
        name="Event Test Field",
        group_id=test_group.id,
        region_id=test_region.id,
        version=1,
        is_current=True,
    )
    db_session.add(field)
    await db_session.flush()
    return field


# ── Unit tests via FieldEventService ───────────────────────────


@pytest.mark.asyncio
async def test_create_event(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.PLANTING,
            crop_year=2024,
            data={"crop": "corn", "variety": "DeKalb DKC64-69"},
        )
    )
    assert event.event_type == EventType.PLANTING
    assert event.crop_year == 2024
    assert event.crop_year_id is not None  # Dual-write: crop_year_id auto-resolved
    assert event.version == 1
    assert event.is_current is True
    assert event.data["crop"] == "corn"


@pytest.mark.asyncio
async def test_create_event_with_entries(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.CROP_PROTECTION,
            crop_year=2024,
            data={"application_method": "broadcast"},
            entries=[
                FieldEventEntryCreate(
                    entry_type="product",
                    data={"name": "Roundup PowerMAX", "rate": 32, "unit": "oz/ac"},
                ),
                FieldEventEntryCreate(
                    entry_type="product",
                    sort_order=1,
                    data={"name": "Atrazine 4L", "rate": 1.5, "unit": "qt/ac"},
                ),
            ],
        )
    )
    entries = await svc.get_entries(event.id)
    assert len(entries) == 2
    assert entries[0].entry_type == "product"


@pytest.mark.asyncio
async def test_event_versioning(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    v1 = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.HARVEST,
            crop_year=2024,
            data={"crop": "corn", "yield_amount": 180, "yield_unit": "bu/ac"},
        )
    )
    assert v1.version == 1

    v2 = await svc.create_new_version(
        v1.id,
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.HARVEST,
            crop_year=2024,
            data={"crop": "corn", "yield_amount": 195, "yield_unit": "bu/ac", "moisture": 15.2},
        ),
    )
    assert v2.version == 2
    assert v2.supersedes_id == v1.id
    assert v2.is_current is True

    # Old version should be non-current
    v1_reloaded = await svc.get_by_id(v1.id)
    assert v1_reloaded.is_current is False


@pytest.mark.asyncio
async def test_version_history(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    v1 = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.FERTILIZING,
            crop_year=2024,
            data={"products": [{"product": "urea", "rate": 150, "unit": "lb/ac"}]},
        )
    )
    v2 = await svc.create_new_version(
        v1.id,
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.FERTILIZING,
            crop_year=2024,
            data={"products": [{"product": "urea", "rate": 175, "unit": "lb/ac"}]},
        ),
    )

    history = await svc.get_version_history(v2.id)
    assert len(history) == 2
    assert history[0].version == 2
    assert history[1].version == 1


@pytest.mark.asyncio
async def test_all_event_types(db_session: AsyncSession, test_field):
    """Ensure all 9 event types can be created."""
    svc = FieldEventService(db_session)
    for et in EventType:
        event = await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=et,
                crop_year=2024,
            )
        )
        assert event.event_type == et


@pytest.mark.asyncio
async def test_list_events_filter_by_type(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    await svc.create_event(
        FieldEventCreate(field_id=test_field.id, event_type=EventType.PLANTING, crop_year=2024)
    )
    await svc.create_event(
        FieldEventCreate(field_id=test_field.id, event_type=EventType.HARVEST, crop_year=2024)
    )

    events, total = await svc.list_events(event_type=EventType.PLANTING)
    assert total == 1
    assert events[0].event_type == EventType.PLANTING


@pytest.mark.asyncio
async def test_soft_delete_event(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(field_id=test_field.id, event_type=EventType.TILLAGE, crop_year=2024)
    )
    await svc.soft_delete(event.id)

    with pytest.raises(Exception):
        await svc.get_by_id(event.id)


@pytest.mark.asyncio
async def test_add_and_remove_entry(db_session: AsyncSession, test_field):
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.SOIL_TESTING,
            crop_year=2024,
        )
    )

    # Add entry
    entry = await svc.add_entry(
        event.id,
        FieldEventEntryCreate(
            entry_type="test_entry",
            data={"nutrient": "P", "value": 42, "unit": "ppm"},
        ),
    )
    assert entry.entry_type == "test_entry"

    entries = await svc.get_entries(event.id)
    assert len(entries) == 1

    # Remove entry
    await svc.remove_entry(entry.id)
    entries = await svc.get_entries(event.id)
    assert len(entries) == 0


# ── API endpoint tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_event(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    # Create a field first
    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "EventAPIField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={
            "field_id": field_id,
            "event_type": "planting",
            "crop_year": 2024,
            "data": {"crop": "soybeans"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["event_type"] == "planting"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_api_get_event_with_entries(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "EntryField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    # Create event with entries
    resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={
            "field_id": field_id,
            "event_type": "crop_protection",
            "crop_year": 2024,
            "entries": [
                {"entry_type": "product", "data": {"name": "Glyphosate"}},
            ],
        },
    )
    event_id = resp.json()["id"]

    # Get with entries
    get_resp = await client.get(f"/api/v1/field-events/{event_id}", headers=_auth(token))
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert len(data["entries"]) == 1
    assert data["entries"][0]["entry_type"] == "product"


@pytest.mark.asyncio
async def test_api_list_events(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "ListEventField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "harvest", "crop_year": 2024},
    )
    await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "planting", "crop_year": 2024},
    )

    resp = await client.get(
        "/api/v1/field-events", headers=_auth(token), params={"field_id": field_id}
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


@pytest.mark.asyncio
async def test_api_update_event(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "UpdateEventField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    create_resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "irrigation", "crop_year": 2024},
    )
    event_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/field-events/{event_id}",
        headers=_auth(token),
        json={"notes": "Applied 1.5 inch"},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Applied 1.5 inch"


@pytest.mark.asyncio
async def test_api_delete_event(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "DeleteEventField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    create_resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "tillage", "crop_year": 2024},
    )
    event_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/field-events/{event_id}", headers=_auth(token))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/field-events/{event_id}", headers=_auth(token))
    assert resp.status_code == 404


# ── ACL enforcement tests ────────────────────────────────────


async def _make_user_in_group(
    db: AsyncSession,
    group: Group,
    username: str,
    password: str = "pass123",
    *,
    is_superuser: bool = False,
) -> User:
    user = User(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.com",
        password_hash=hash_password(password),
        full_name=username.title(),
        is_active=True,
        is_superuser=is_superuser,
        group_id=group.id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_acl_append_only_can_post_not_patch(
    client: AsyncClient, db_session, test_group, test_region
):
    """User with fielddata.append=GRANT, fielddata.modify=DENY can POST but not PATCH."""
    append_group = Group(id=uuid.uuid4(), name="AppendOnlyEventGroup")
    db_session.add(append_group)
    await db_session.flush()

    # Field permissions so we can create a field
    field_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=append_group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.create": PermissionState.GRANT,
        },
    )
    db_session.add(field_priv)

    # Append-only fielddata
    fd_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=append_group.id,
        resource_type="fielddata",
        resource_id=None,
        permissions={
            "fielddata.read": PermissionState.GRANT,
            "fielddata.append": PermissionState.GRANT,
            "fielddata.modify": PermissionState.DENY,
        },
    )
    db_session.add(fd_priv)
    region = Region(id=uuid.uuid4(), name="AppendEventRegion", group_id=append_group.id)
    db_session.add(region)
    await db_session.flush()

    await _make_user_in_group(db_session, append_group, "append_event_user")
    token = await _login(client, "append_event_user", "pass123")

    # Create field
    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "AppendEventField",
            "group_id": str(append_group.id),
            "region_id": str(region.id),
        },
    )
    assert field_resp.status_code == 201
    field_id = field_resp.json()["id"]

    # POST event should succeed (append=GRANT)
    resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "planting", "crop_year": 2024},
    )
    assert resp.status_code == 201
    event_id = resp.json()["id"]

    # PATCH event should fail (modify=DENY)
    resp = await client.patch(
        f"/api/v1/field-events/{event_id}",
        headers=_auth(token),
        json={"notes": "Updated"},
    )
    assert resp.status_code == 403

    # DELETE event should also fail (modify=DENY)
    resp = await client.delete(f"/api/v1/field-events/{event_id}", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_modify_only_can_patch_not_post(
    client: AsyncClient, db_session, test_group, test_region
):
    """User with fielddata.modify=GRANT, fielddata.append=DENY can PATCH but not POST."""
    mod_group = Group(id=uuid.uuid4(), name="ModifyOnlyEventGroup")
    db_session.add(mod_group)
    await db_session.flush()

    field_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=mod_group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.create": PermissionState.GRANT,
        },
    )
    db_session.add(field_priv)

    fd_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=mod_group.id,
        resource_type="fielddata",
        resource_id=None,
        permissions={
            "fielddata.read": PermissionState.GRANT,
            "fielddata.append": PermissionState.DENY,
            "fielddata.modify": PermissionState.GRANT,
        },
    )
    db_session.add(fd_priv)
    region = Region(id=uuid.uuid4(), name="ModEventRegion", group_id=mod_group.id)
    db_session.add(region)
    await db_session.flush()

    await _make_user_in_group(db_session, mod_group, "modify_event_user")
    token = await _login(client, "modify_event_user", "pass123")

    # Create field (via su so we have a field to work with)
    await _make_user_in_group(db_session, mod_group, "su_for_event", is_superuser=True)
    su_token = await _login(client, "su_for_event", "pass123")

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(su_token),
        json={
            "name": "ModEventField",
            "group_id": str(mod_group.id),
            "region_id": str(region.id),
        },
    )
    field_id = field_resp.json()["id"]

    # POST event should fail (append=DENY)
    resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": field_id, "event_type": "harvest", "crop_year": 2024},
    )
    assert resp.status_code == 403

    # Create event as superuser so modify user can PATCH it
    ev_resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(su_token),
        json={"field_id": field_id, "event_type": "harvest", "crop_year": 2024},
    )
    event_id = ev_resp.json()["id"]

    # PATCH should succeed (modify=GRANT)
    resp = await client.patch(
        f"/api/v1/field-events/{event_id}",
        headers=_auth(token),
        json={"notes": "Modified OK"},
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Modified OK"


@pytest.mark.asyncio
async def test_acl_no_fielddata_perms_denied(client: AsyncClient, db_session):
    """User with no fielddata permissions gets denied / empty list."""
    no_perm_group = Group(id=uuid.uuid4(), name="NoFielddataPermsGroup")
    db_session.add(no_perm_group)
    await db_session.flush()

    await _make_user_in_group(db_session, no_perm_group, "no_fd_perm_user")
    token = await _login(client, "no_fd_perm_user", "pass123")

    # List returns empty
    resp = await client.get("/api/v1/field-events", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # POST should be denied
    resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={"field_id": str(uuid.uuid4()), "event_type": "planting", "crop_year": 2024},
    )
    assert resp.status_code == 403


# ── Per-subtype schema validation tests ──────────────────────


@pytest.mark.asyncio
async def test_planting_valid(db_session: AsyncSession, test_field):
    """Planting with required fields passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.PLANTING,
            crop_year=2024,
            data={"crop": "corn", "variety": "P0589", "seed_rate": 32000},
        )
    )
    assert event.data["crop"] == "corn"
    assert event.data["variety"] == "P0589"


@pytest.mark.asyncio
async def test_planting_missing_crop_rejected(db_session: AsyncSession, test_field):
    """Planting without 'crop' is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="crop"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.PLANTING,
                crop_year=2024,
                data={"variety": "P0589"},
            )
        )


@pytest.mark.asyncio
async def test_crop_protection_valid(db_session: AsyncSession, test_field):
    """Crop protection with products passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.CROP_PROTECTION,
            crop_year=2024,
            data={
                "target_pest": "broadleaf weeds",
                "products": [
                    {"product": "Roundup PowerMAX", "rate": 32, "unit": "oz/ac"},
                ],
            },
        )
    )
    assert event.data["target_pest"] == "broadleaf weeds"
    assert len(event.data["products"]) == 1


@pytest.mark.asyncio
async def test_harvest_valid(db_session: AsyncSession, test_field):
    """Harvest with all required fields passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.HARVEST,
            crop_year=2024,
            data={
                "crop": "corn",
                "yield_amount": 210.5,
                "yield_unit": "bu/ac",
                "moisture": 15.2,
                "test_weight": 56.0,
            },
        )
    )
    assert event.data["yield_amount"] == 210.5
    assert event.data["moisture"] == 15.2


@pytest.mark.asyncio
async def test_harvest_missing_required_rejected(db_session: AsyncSession, test_field):
    """Harvest without yield_amount is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="yield_amount"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.HARVEST,
                crop_year=2024,
                data={"crop": "corn", "yield_unit": "bu/ac"},
            )
        )


@pytest.mark.asyncio
async def test_fertilizing_valid(db_session: AsyncSession, test_field):
    """Fertilizing with product list passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.FERTILIZING,
            crop_year=2024,
            data={
                "products": [
                    {"product": "UAN 32%", "rate": 40, "unit": "gal/ac"},
                    {"product": "AMS", "rate": 2.5, "unit": "lb/ac"},
                ],
            },
        )
    )
    assert len(event.data["products"]) == 2


@pytest.mark.asyncio
async def test_fertilizing_empty_products_rejected(db_session: AsyncSession, test_field):
    """Fertilizing with empty products list is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="products"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.FERTILIZING,
                crop_year=2024,
                data={"products": []},
            )
        )


@pytest.mark.asyncio
async def test_scouting_valid_with_entries(db_session: AsyncSession, test_field):
    """Scouting event with entry rows for weeds and diseases."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.SCOUTING,
            crop_year=2024,
            data={"scout_name": "John", "growth_stage": "V6"},
            entries=[
                FieldEventEntryCreate(
                    entry_type="weeds",
                    data={"species": "waterhemp", "density": "high"},
                ),
                FieldEventEntryCreate(
                    entry_type="diseases",
                    sort_order=1,
                    data={"disease": "gray leaf spot", "severity": "moderate"},
                ),
            ],
        )
    )
    entries = await svc.get_entries(event.id)
    assert len(entries) == 2
    types = {e.entry_type for e in entries}
    assert types == {"weeds", "diseases"}


@pytest.mark.asyncio
async def test_soil_testing_valid(db_session: AsyncSession, test_field):
    """Soil testing with in-range values passes with no issues."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.SOIL_TESTING,
            crop_year=2024,
            data={
                "lab_name": "Ward Labs",
                "test_entries": [
                    {"parameter": "pH", "value": 6.8, "unit": ""},
                    {"parameter": "P", "value": 42, "unit": "ppm"},
                    {"parameter": "K", "value": 280, "unit": "ppm"},
                ],
            },
        )
    )
    assert len(event.data["test_entries"]) == 3
    assert len(event.data["validation_issues"]) == 0


@pytest.mark.asyncio
async def test_soil_testing_out_of_range_warns(db_session: AsyncSession, test_field):
    """Soil testing with out-of-range values still saves but adds warnings."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.SOIL_TESTING,
            crop_year=2024,
            data={
                "test_entries": [
                    {"parameter": "pH", "value": 12.0, "unit": ""},
                    {"parameter": "P", "value": 600, "unit": "ppm"},
                ],
            },
        )
    )
    issues = event.data["validation_issues"]
    assert len(issues) == 2
    params = {i["parameter"] for i in issues}
    assert params == {"pH", "P"}


@pytest.mark.asyncio
async def test_soil_testing_empty_entries_rejected(db_session: AsyncSession, test_field):
    """Soil testing with empty test_entries is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="test_entries"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.SOIL_TESTING,
                crop_year=2024,
                data={"test_entries": []},
            )
        )


@pytest.mark.asyncio
async def test_tillage_valid(db_session: AsyncSession, test_field):
    """Tillage with valid type passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.TILLAGE,
            crop_year=2024,
            data={"tillage_type": "no_till"},
        )
    )
    assert event.data["tillage_type"] == "no_till"


@pytest.mark.asyncio
async def test_tillage_invalid_type_rejected(db_session: AsyncSession, test_field):
    """Tillage with invalid tillage_type is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="tillage_type"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.TILLAGE,
                crop_year=2024,
                data={"tillage_type": "rocket_propelled"},
            )
        )


@pytest.mark.asyncio
async def test_irrigation_valid(db_session: AsyncSession, test_field):
    """Irrigation with valid data passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.IRRIGATION,
            crop_year=2024,
            data={"volume": 1.5, "volume_unit": "in", "method": "center_pivot"},
        )
    )
    assert event.data["volume"] == 1.5


@pytest.mark.asyncio
async def test_irrigation_missing_volume_rejected(db_session: AsyncSession, test_field):
    """Irrigation without volume is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="volume"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.IRRIGATION,
                crop_year=2024,
                data={"volume_unit": "in"},
            )
        )


@pytest.mark.asyncio
async def test_insurance_valid(db_session: AsyncSession, test_field):
    """Insurance with valid data including prevented planting passes."""
    svc = FieldEventService(db_session)
    event = await svc.create_event(
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.INSURANCE,
            crop_year=2024,
            data={
                "fcic_crop_code": "0041",
                "policy_number": "POL-2024-001",
                "prevented_planting": {
                    "reason": "flooding",
                    "acres_affected": 45.5,
                    "intended_crop": "corn",
                },
            },
        )
    )
    assert event.data["fcic_crop_code"] == "0041"
    assert event.data["prevented_planting"]["acres_affected"] == 45.5


@pytest.mark.asyncio
async def test_insurance_missing_crop_code_rejected(db_session: AsyncSession, test_field):
    """Insurance without fcic_crop_code is rejected."""
    svc = FieldEventService(db_session)
    with pytest.raises(Exception, match="fcic_crop_code"):
        await svc.create_event(
            FieldEventCreate(
                field_id=test_field.id,
                event_type=EventType.INSURANCE,
                crop_year=2024,
                data={"policy_number": "POL-2024-001"},
            )
        )


# ── History endpoint test (Task #15) ─────────────────────────


@pytest.mark.asyncio
async def test_api_history_endpoint(client: AsyncClient, test_user, test_group, test_region):
    """Create v1, PATCH to v2, PATCH to v3 — history returns 3 in chrono order."""
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "HistoryField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    field_id = field_resp.json()["id"]

    # v1
    v1_resp = await client.post(
        "/api/v1/field-events",
        headers=_auth(token),
        json={
            "field_id": field_id,
            "event_type": "planting",
            "crop_year": 2024,
            "data": {"crop": "corn"},
        },
    )
    assert v1_resp.status_code == 201
    v1_id = v1_resp.json()["id"]

    # v2 (new version of v1)
    v2_resp = await client.post(
        f"/api/v1/field-events/{v1_id}/versions",
        headers=_auth(token),
        json={
            "field_id": field_id,
            "event_type": "planting",
            "crop_year": 2024,
            "data": {"crop": "corn", "variety": "P0589"},
        },
    )
    assert v2_resp.status_code == 201
    v2_id = v2_resp.json()["id"]

    # v3 (new version of v2)
    v3_resp = await client.post(
        f"/api/v1/field-events/{v2_id}/versions",
        headers=_auth(token),
        json={
            "field_id": field_id,
            "event_type": "planting",
            "crop_year": 2024,
            "data": {"crop": "corn", "variety": "P0589", "seed_rate": 32000},
        },
    )
    assert v3_resp.status_code == 201
    v3_id = v3_resp.json()["id"]

    # Get history — should be in chronological order (v1, v2, v3)
    history_resp = await client.get(
        f"/api/v1/field-events/{v3_id}/history",
        headers=_auth(token),
    )
    assert history_resp.status_code == 200
    versions = history_resp.json()["versions"]
    assert len(versions) == 3
    assert versions[0]["version"] == 1
    assert versions[1]["version"] == 2
    assert versions[2]["version"] == 3
