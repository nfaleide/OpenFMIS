"""Region tests — CRUD + many-to-many field membership."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.schemas.region import RegionCreate, RegionUpdate
from openfmis.services.region import RegionService


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
    group = Group(id=uuid.uuid4(), name="RegionCo")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_fields(db_session: AsyncSession, test_group: Group) -> list[Field]:
    """Create 3 test fields for membership tests."""
    fields = []
    for name in ["Field A", "Field B", "Field C"]:
        f = Field(
            id=uuid.uuid4(),
            name=name,
            group_id=test_group.id,
            version=1,
            is_current=True,
        )
        db_session.add(f)
        fields.append(f)
    await db_session.flush()
    return fields


# ── Unit tests via RegionService ───────────────────────────────


@pytest.mark.asyncio
async def test_create_region(db_session: AsyncSession, test_group):
    svc = RegionService(db_session)
    region = await svc.create_region(RegionCreate(name="North Region", group_id=test_group.id))
    assert region.name == "North Region"
    assert region.is_private is False


@pytest.mark.asyncio
async def test_create_region_with_fields(db_session: AsyncSession, test_group, test_fields):
    svc = RegionService(db_session)
    field_ids = [f.id for f in test_fields[:2]]
    region = await svc.create_region(
        RegionCreate(name="With Fields", group_id=test_group.id, field_ids=field_ids)
    )
    members = await svc.get_member_field_ids(region.id)
    assert len(members) == 2
    assert set(members) == set(field_ids)


@pytest.mark.asyncio
async def test_add_and_remove_members(db_session: AsyncSession, test_group, test_fields):
    svc = RegionService(db_session)
    region = await svc.create_region(RegionCreate(name="Membership Test", group_id=test_group.id))

    # Add 2 fields
    added = await svc.add_members(region.id, [test_fields[0].id, test_fields[1].id])
    assert added == 2

    # Add again — should skip duplicates
    added2 = await svc.add_members(region.id, [test_fields[0].id, test_fields[2].id])
    assert added2 == 1  # Only field C is new

    members = await svc.get_member_field_ids(region.id)
    assert len(members) == 3

    # Remove 1
    removed = await svc.remove_members(region.id, [test_fields[1].id])
    assert removed == 1

    members = await svc.get_member_field_ids(region.id)
    assert len(members) == 2


@pytest.mark.asyncio
async def test_get_regions_for_field(db_session: AsyncSession, test_group, test_fields):
    svc = RegionService(db_session)
    await svc.create_region(
        RegionCreate(name="Region 1", group_id=test_group.id, field_ids=[test_fields[0].id])
    )
    await svc.create_region(
        RegionCreate(name="Region 2", group_id=test_group.id, field_ids=[test_fields[0].id])
    )

    regions = await svc.get_regions_for_field(test_fields[0].id)
    assert len(regions) == 2
    region_names = {r.name for r in regions}
    assert "Region 1" in region_names
    assert "Region 2" in region_names


@pytest.mark.asyncio
async def test_update_region(db_session: AsyncSession, test_group):
    svc = RegionService(db_session)
    region = await svc.create_region(RegionCreate(name="OldName", group_id=test_group.id))
    updated = await svc.update_region(region.id, RegionUpdate(name="NewName", is_private=True))
    assert updated.name == "NewName"
    assert updated.is_private is True


@pytest.mark.asyncio
async def test_soft_delete_region(db_session: AsyncSession, test_group):
    svc = RegionService(db_session)
    region = await svc.create_region(RegionCreate(name="DeleteMe", group_id=test_group.id))
    await svc.soft_delete(region.id)

    with pytest.raises(Exception):
        await svc.get_by_id(region.id)


@pytest.mark.asyncio
async def test_list_regions(db_session: AsyncSession, test_group, test_fields):
    svc = RegionService(db_session)
    await svc.create_region(
        RegionCreate(name="List1", group_id=test_group.id, field_ids=[test_fields[0].id])
    )
    await svc.create_region(RegionCreate(name="List2", group_id=test_group.id))

    regions, counts, total = await svc.list_regions(group_id=test_group.id)
    assert total == 2
    assert len(regions) == 2
    # Find the one with a member
    idx = next(i for i, r in enumerate(regions) if r.name == "List1")
    assert counts[idx] == 1


# ── API endpoint tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_region(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "API Region", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Region"
    assert data["field_count"] == 0


@pytest.mark.asyncio
async def test_api_get_region(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Detail Region", "group_id": str(test_group.id)},
    )
    region_id = create_resp.json()["id"]

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Detail Region"
    assert "field_ids" in data


@pytest.mark.asyncio
async def test_api_list_regions(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    await client.post(
        "/api/v1/regions", headers=_auth(token), json={"name": "R1", "group_id": str(test_group.id)}
    )
    await client.post(
        "/api/v1/regions", headers=_auth(token), json={"name": "R2", "group_id": str(test_group.id)}
    )

    resp = await client.get("/api/v1/regions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_api_update_region(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "OrigName", "group_id": str(test_group.id)},
    )
    region_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/regions/{region_id}",
        headers=_auth(token),
        json={"name": "NewName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


@pytest.mark.asyncio
async def test_api_delete_region(client: AsyncClient, test_user, test_group):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "ToDelete", "group_id": str(test_group.id)},
    )
    region_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_add_and_remove_members(client: AsyncClient, test_user, test_group):
    token = await _login(client)

    # Create a field
    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "MemberField", "group_id": str(test_group.id)},
    )
    field_id = field_resp.json()["id"]

    # Create a region
    region_resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "MemberRegion", "group_id": str(test_group.id)},
    )
    region_id = region_resp.json()["id"]

    # Add field to region
    add_resp = await client.post(
        f"/api/v1/regions/{region_id}/members",
        headers=_auth(token),
        json={"field_ids": [field_id]},
    )
    assert add_resp.status_code == 200
    assert field_id in add_resp.json()["field_ids"]
    assert add_resp.json()["field_count"] == 1

    # Remove field from region
    rem_resp = await client.request(
        "DELETE",
        f"/api/v1/regions/{region_id}/members",
        headers=_auth(token),
        json={"field_ids": [field_id]},
    )
    assert rem_resp.status_code == 200
    assert rem_resp.json()["field_count"] == 0
