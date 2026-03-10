"""FieldEvent tests — CRUD, versioning, sub-entries, all 9 event types."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.field_event import EventType
from openfmis.models.group import Group
from openfmis.schemas.field_event import FieldEventCreate, FieldEventEntryCreate
from openfmis.services.field_event import FieldEventService


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "testuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="EventCo")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_field(db_session: AsyncSession, test_group: Group) -> Field:
    field = Field(
        id=uuid.uuid4(),
        name="Event Test Field",
        group_id=test_group.id,
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
            data={"yield_bu_ac": 180},
        )
    )
    assert v1.version == 1

    v2 = await svc.create_new_version(
        v1.id,
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.HARVEST,
            crop_year=2024,
            data={"yield_bu_ac": 195, "moisture": 15.2},
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
            data={"product": "urea"},
        )
    )
    v2 = await svc.create_new_version(
        v1.id,
        FieldEventCreate(
            field_id=test_field.id,
            event_type=EventType.FERTILIZING,
            crop_year=2024,
            data={"product": "urea", "rate": 150},
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
async def test_api_create_event(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    # Create a field first
    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "EventAPIField", "group_id": str(test_group.id)},
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
async def test_api_get_event_with_entries(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "EntryField", "group_id": str(test_group.id)},
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
async def test_api_list_events(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "ListEventField", "group_id": str(test_group.id)},
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
async def test_api_update_event(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "UpdateEventField", "group_id": str(test_group.id)},
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
async def test_api_delete_event(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "DeleteEventField", "group_id": str(test_group.id)},
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
