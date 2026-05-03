"""Equipment tests — CRUD + group-scoped ACL enforcement."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege
from openfmis.models.user import User
from openfmis.schemas.equipment import EquipmentCreate, EquipmentUpdate
from openfmis.security.password import hash_password
from openfmis.services.equipment import EquipmentService


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
    group = Group(id=uuid.uuid4(), name="EquipCo")
    db_session.add(group)
    await db_session.flush()
    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="groups",
        resource_id=None,
        permissions={"change_group_settings": "GRANT"},
    )
    db_session.add(priv)
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
async def test_acl_cross_group_leak(client: AsyncClient, db_session, test_group):
    """User cannot see equipment from another group."""
    # Create equipment in test_group via superuser
    await _make_user_in_group(db_session, test_group, "su_equip", is_superuser=True)
    su_token = await _login(client, "su_equip", "pass123")
    create_resp = await client.post(
        "/api/v1/equipment",
        headers=_auth(su_token),
        json={"group_id": str(test_group.id), "name": "Hidden Tractor"},
    )
    equip_id = create_resp.json()["id"]

    # Create other group + user
    other_group = Group(id=uuid.uuid4(), name="OtherEquipGroup")
    db_session.add(other_group)
    await db_session.flush()

    await _make_user_in_group(db_session, other_group, "other_equip_user")
    other_token = await _login(client, "other_equip_user", "pass123")

    # List should be empty (scoped to other_group)
    resp = await client.get("/api/v1/equipment", headers=_auth(other_token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Direct get should fail (different group)
    resp = await client.get(f"/api/v1/equipment/{equip_id}", headers=_auth(other_token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_no_group_settings_cannot_create(client: AsyncClient, db_session):
    """User without change_group_settings cannot create/update/delete equipment."""
    no_admin_group = Group(id=uuid.uuid4(), name="NoAdminEquipGroup")
    db_session.add(no_admin_group)
    await db_session.flush()

    # No change_group_settings privilege
    await _make_user_in_group(db_session, no_admin_group, "no_admin_equip")
    token = await _login(client, "no_admin_equip", "pass123")

    # Create should be denied
    resp = await client.post(
        "/api/v1/equipment",
        headers=_auth(token),
        json={"group_id": str(no_admin_group.id), "name": "Nope"},
    )
    assert resp.status_code == 403

    # List still works (group membership check, not ACL)
    resp = await client.get("/api/v1/equipment", headers=_auth(token))
    assert resp.status_code == 200
