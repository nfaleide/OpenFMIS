"""Equipment tests — CRUD."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.schemas.equipment import EquipmentCreate, EquipmentUpdate
from openfmis.services.equipment import EquipmentService


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
    group = Group(id=uuid.uuid4(), name="EquipCo")
    db_session.add(group)
    await db_session.flush()
    return group


# ── Unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_equipment(db_session: AsyncSession, test_group):
    svc = EquipmentService(db_session)
    equip = await svc.create_equipment(
        EquipmentCreate(
            group_id=test_group.id,
            name="John Deere 8R",
            make="John Deere",
            model="8R 370",
            year=2023,
            equipment_type="tractor",
        )
    )
    assert equip.name == "John Deere 8R"
    assert equip.equipment_type == "tractor"


@pytest.mark.asyncio
async def test_update_equipment(db_session: AsyncSession, test_group):
    svc = EquipmentService(db_session)
    equip = await svc.create_equipment(EquipmentCreate(group_id=test_group.id, name="Old Sprayer"))
    updated = await svc.update_equipment(equip.id, EquipmentUpdate(name="New Sprayer", year=2024))
    assert updated.name == "New Sprayer"
    assert updated.year == 2024


@pytest.mark.asyncio
async def test_list_equipment_by_type(db_session: AsyncSession, test_group):
    svc = EquipmentService(db_session)
    await svc.create_equipment(
        EquipmentCreate(group_id=test_group.id, name="Tractor A", equipment_type="tractor")
    )
    await svc.create_equipment(
        EquipmentCreate(group_id=test_group.id, name="Sprayer B", equipment_type="sprayer")
    )
    equipment, total = await svc.list_equipment(equipment_type="tractor")
    assert total == 1
    assert equipment[0].name == "Tractor A"


@pytest.mark.asyncio
async def test_soft_delete_equipment(db_session: AsyncSession, test_group):
    svc = EquipmentService(db_session)
    equip = await svc.create_equipment(EquipmentCreate(group_id=test_group.id, name="DeleteMe"))
    await svc.soft_delete(equip.id)
    with pytest.raises(Exception):
        await svc.get_by_id(equip.id)


# ── API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_equipment(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/equipment",
        headers=_auth(token),
        json={
            "group_id": str(test_group.id),
            "name": "API Combine",
            "make": "Case IH",
            "equipment_type": "combine",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "API Combine"


@pytest.mark.asyncio
async def test_api_list_equipment(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    await client.post(
        "/api/v1/equipment",
        headers=_auth(token),
        json={"group_id": str(test_group.id), "name": "E1"},
    )
    await client.post(
        "/api/v1/equipment",
        headers=_auth(token),
        json={"group_id": str(test_group.id), "name": "E2"},
    )
    resp = await client.get("/api/v1/equipment", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_api_delete_equipment(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/equipment",
        headers=_auth(token),
        json={"group_id": str(test_group.id), "name": "ToDelete"},
    )
    equip_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/v1/equipment/{equip_id}", headers=_auth(token))
    assert resp.status_code == 204
