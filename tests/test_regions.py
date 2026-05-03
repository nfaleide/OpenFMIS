"""Region tests — CRUD + many-to-many field membership + ACL enforcement."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege, PermissionState, UserPrivilege
from openfmis.models.region import Region
from openfmis.models.user import User
from openfmis.schemas.privilege import PrivilegeGrant
from openfmis.schemas.region import RegionCreate, RegionUpdate
from openfmis.security.password import hash_password
from openfmis.services.acl import ACLService
from openfmis.services.region import RegionService


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
    from openfmis.models.privilege import GroupPrivilege

    group = Group(id=uuid.uuid4(), name="RegionCo")
    db_session.add(group)
    await db_session.flush()
    priv = GroupPrivilege(
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
    db_session.add(priv)
    region_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="regions",
        resource_id=None,
        permissions={
            "regions.read": "GRANT",
            "regions.create": "GRANT",
            "regions.modify": "GRANT",
            "regions.delete": "GRANT",
        },
    )
    db_session.add(region_priv)
    await db_session.flush()
    return group


@pytest.fixture
async def test_region(db_session: AsyncSession, test_group: Group) -> Region:
    region = Region(id=uuid.uuid4(), name="Test Farm", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()
    return region


@pytest.fixture
async def test_fields(
    db_session: AsyncSession, test_group: Group, test_region: Region
) -> list[Field]:
    """Create 3 test fields for membership tests."""
    fields = []
    for name in ["Field A", "Field B", "Field C"]:
        f = Field(
            id=uuid.uuid4(),
            name=name,
            group_id=test_group.id,
            region_id=test_region.id,
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
    assert total == 3  # test_region fixture + List1 + List2
    assert len(regions) == 3
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
async def test_api_add_and_remove_members(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    # Create a field
    field_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "MemberField",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
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
async def test_acl_superuser_allowed(client: AsyncClient, db_session, test_group):
    """Superusers bypass all ACL checks on regions."""
    await _make_user_in_group(db_session, test_group, "su_regions", is_superuser=True)
    token = await _login(client, "su_regions", "pass123")

    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "SU Region", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201
    region_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200

    resp = await client.get("/api/v1/regions", headers=_auth(token))
    assert resp.status_code == 200

    resp = await client.patch(
        f"/api/v1/regions/{region_id}",
        headers=_auth(token),
        json={"name": "Renamed"},
    )
    assert resp.status_code == 200

    resp = await client.delete(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_acl_group_grant_allowed(client: AsyncClient, db_session, test_group):
    """User in a group with GRANT on regions.* can do everything."""
    await _make_user_in_group(db_session, test_group, "granted_region_user")
    token = await _login(client, "granted_region_user", "pass123")

    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Granted Region", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201
    region_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200

    resp = await client.get("/api/v1/regions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_acl_user_deny_overrides_group_grant(client: AsyncClient, db_session, test_group):
    """User-level DENY overrides group-level GRANT on regions."""
    user = await _make_user_in_group(db_session, test_group, "denied_region_user")

    user_priv = UserPrivilege(
        id=uuid.uuid4(),
        user_id=user.id,
        resource_type="regions",
        resource_id=None,
        permissions={"regions.read": PermissionState.DENY},
    )
    db_session.add(user_priv)
    await db_session.flush()

    token = await _login(client, "denied_region_user", "pass123")

    # List should return empty (DENY on read)
    resp = await client.get("/api/v1/regions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Create a region as superuser so we have something to try to read
    await _make_user_in_group(db_session, test_group, "su_for_region_deny", is_superuser=True)
    su_token = await _login(client, "su_for_region_deny", "pass123")
    create_resp = await client.post(
        "/api/v1/regions",
        headers=_auth(su_token),
        json={"name": "Hidden Region", "group_id": str(test_group.id)},
    )
    region_id = create_resp.json()["id"]

    # Get should be denied
    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_no_entry_denied(client: AsyncClient, db_session):
    """User in a group with NO permission entries → default DENY."""
    other_group = Group(id=uuid.uuid4(), name="NoRegionPermsGroup")
    db_session.add(other_group)
    await db_session.flush()

    await _make_user_in_group(db_session, other_group, "noperm_region_user")
    token = await _login(client, "noperm_region_user", "pass123")

    # List returns empty (not 403)
    resp = await client.get("/api/v1/regions", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Create should be denied
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Nope", "group_id": str(other_group.id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_append_only_region_user(client: AsyncClient, db_session):
    """User with regions.create=GRANT but regions.modify=DENY can POST but not PATCH."""
    append_group = Group(id=uuid.uuid4(), name="AppendOnlyRegionGroup")
    db_session.add(append_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=append_group.id,
        resource_type="regions",
        resource_id=None,
        permissions={
            "regions.read": PermissionState.GRANT,
            "regions.create": PermissionState.GRANT,
            "regions.modify": PermissionState.DENY,
            "regions.delete": PermissionState.DENY,
        },
    )
    db_session.add(priv)
    await db_session.flush()

    await _make_user_in_group(db_session, append_group, "append_region_user")
    token = await _login(client, "append_region_user", "pass123")

    # Create should work
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Append Region", "group_id": str(append_group.id)},
    )
    assert resp.status_code == 201
    region_id = resp.json()["id"]

    # PATCH should be denied
    resp = await client.patch(
        f"/api/v1/regions/{region_id}",
        headers=_auth(token),
        json={"name": "Changed"},
    )
    assert resp.status_code == 403

    # DELETE should be denied
    resp = await client.delete(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 403


# ── Accessible-set tests ───────────────��────────────────────


@pytest.mark.asyncio
async def test_accessible_set_superuser_sees_all(db_session: AsyncSession):
    """Superuser sees all regions and fields."""
    group = Group(id=uuid.uuid4(), name="AccSetGroup")
    db_session.add(group)
    await db_session.flush()

    region = Region(id=uuid.uuid4(), name="AccRegion", group_id=group.id)
    db_session.add(region)
    await db_session.flush()

    field = Field(
        id=uuid.uuid4(),
        name="AccField",
        group_id=group.id,
        region_id=region.id,
        version=1,
        is_current=True,
        geometry="SRID=4326;MULTIPOLYGON(((-97 40,-97.01 40,-97.01 40.01,-97 40.01,-97 40)))",
    )
    db_session.add(field)
    await db_session.flush()

    su = User(
        id=uuid.uuid4(),
        username="acc_su",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=True,
    )
    db_session.add(su)
    await db_session.flush()

    svc = RegionService(db_session)
    result = await svc.get_accessible_set(su)
    assert result.total_regions >= 1
    assert result.total_fields >= 1
    region_ids = {r.id for r in result.regions}
    assert region.id in region_ids


@pytest.mark.asyncio
async def test_accessible_set_mixed_acl(db_session: AsyncSession):
    """Parity test: mixed ACL grants produce the expected accessible set.

    Setup:
    - Group with fields.read + regions.read GRANT
    - 3 regions: public1, public2, private1 (created by another user)
    - 3 fields: field1 in public1, field2 in public2, field3 in private1
    - User-level DENY on field2 specifically
    Expected: user sees public1 (with field1), public2 (0 fields — field2 denied),
              but NOT private1 (created by someone else, same group)
    """
    group = Group(id=uuid.uuid4(), name="MixedACLGroup")
    db_session.add(group)
    await db_session.flush()

    # Grant group-wide read
    acl = ACLService(db_session)
    await acl.grant_group_privilege(
        group.id,
        PrivilegeGrant(
            resource_type="fields",
            permissions={"fields.read": "GRANT"},
        ),
    )
    await acl.grant_group_privilege(
        group.id,
        PrivilegeGrant(
            resource_type="regions",
            permissions={"regions.read": "GRANT"},
        ),
    )

    other_user = User(
        id=uuid.uuid4(),
        username="other_creator",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(other_user)
    await db_session.flush()

    # Create regions
    public1 = Region(id=uuid.uuid4(), name="Public1", group_id=group.id, is_private=False)
    public2 = Region(id=uuid.uuid4(), name="Public2", group_id=group.id, is_private=False)
    private1 = Region(
        id=uuid.uuid4(),
        name="Private1",
        group_id=group.id,
        is_private=True,
        created_by=other_user.id,
    )
    db_session.add_all([public1, public2, private1])
    await db_session.flush()

    # Create fields
    field1 = Field(
        id=uuid.uuid4(),
        name="Field1",
        group_id=group.id,
        region_id=public1.id,
        version=1,
        is_current=True,
        geometry="SRID=4326;MULTIPOLYGON(((-97 40,-97.01 40,-97.01 40.01,-97 40.01,-97 40)))",
    )
    field2 = Field(
        id=uuid.uuid4(),
        name="Field2",
        group_id=group.id,
        region_id=public2.id,
        version=1,
        is_current=True,
        geometry="SRID=4326;MULTIPOLYGON(((-97 40,-97.01 40,-97.01 40.01,-97 40.01,-97 40)))",
    )
    field3 = Field(
        id=uuid.uuid4(),
        name="Field3",
        group_id=group.id,
        region_id=private1.id,
        version=1,
        is_current=True,
        geometry="SRID=4326;MULTIPOLYGON(((-97 40,-97.01 40,-97.01 40.01,-97 40.01,-97 40)))",
    )
    db_session.add_all([field1, field2, field3])
    await db_session.flush()

    # Create target user
    user = User(
        id=uuid.uuid4(),
        username="mixed_acl_user",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    # DENY field2 specifically for this user
    await acl.grant_user_privilege(
        user.id,
        PrivilegeGrant(
            resource_type="fields",
            resource_id=field2.id,
            permissions={"fields.read": "DENY"},
        ),
    )

    svc = RegionService(db_session)
    result = await svc.get_accessible_set(user)

    region_map = {r.name: r for r in result.regions}

    # Public1 visible with field1
    assert "Public1" in region_map
    assert field1.id in region_map["Public1"].field_ids
    assert region_map["Public1"].field_count == 1

    # Public2 visible but field2 is denied
    assert "Public2" in region_map
    assert field2.id not in region_map["Public2"].field_ids
    assert region_map["Public2"].field_count == 0

    # Private1 NOT visible (created by other_user, same group level)
    assert "Private1" not in region_map

    # Total: 2 regions, 1 field
    assert result.total_regions == 2
    assert result.total_fields == 1


@pytest.mark.asyncio
async def test_accessible_set_no_permissions(db_session: AsyncSession):
    """User with no permissions sees empty set."""
    group = Group(id=uuid.uuid4(), name="NoPermGroup")
    db_session.add(group)
    await db_session.flush()

    region = Region(id=uuid.uuid4(), name="Hidden", group_id=group.id)
    db_session.add(region)
    await db_session.flush()

    user = User(
        id=uuid.uuid4(),
        username="noperm_acc",
        password_hash=hash_password("pw"),
        is_active=True,
        is_superuser=False,
        group_id=group.id,
    )
    db_session.add(user)
    await db_session.flush()

    svc = RegionService(db_session)
    result = await svc.get_accessible_set(user)
    assert result.total_regions == 0
    assert result.total_fields == 0


@pytest.mark.asyncio
async def test_accessible_set_api(
    client: AsyncClient, test_user, test_group, test_region, test_field
):
    """API endpoint returns accessible set."""
    token = await _login(client)
    resp = await client.get("/api/v1/regions/accessible", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_regions"] >= 1
    assert data["total_fields"] >= 1


@pytest.mark.asyncio
async def test_api_my_regions(client: AsyncClient, test_user, test_group):
    """GET /regions/mine returns only regions created by the current user."""
    token = await _login(client)

    # Create a region as the test user
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "My Region", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201

    resp = await client.get("/api/v1/regions/mine", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(r["created_by"] == str(test_user.id) for r in data["items"])


@pytest.mark.asyncio
async def test_api_visible_regions(client: AsyncClient, test_user, test_group, test_region):
    """GET /regions/visible returns ACL-visible regions."""
    token = await _login(client)

    resp = await client.get("/api/v1/regions/visible", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    region_ids = [r["id"] for r in data["items"]]
    assert str(test_region.id) in region_ids


# ── Region detail: area + accessibility tests ──────────────────


@pytest.mark.asyncio
async def test_region_detail_includes_area_and_accessibility(
    client: AsyncClient, test_user, test_group
):
    """GET /regions/{id} returns total_area_acres and accessibility."""
    token = await _login(client)
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Detail Farm", "group_id": str(test_group.id)},
    )
    assert resp.status_code == 201
    region_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()

    assert "total_area_acres" in data
    assert "accessibility" in data
    assert data["accessibility"]["can_read"] is True
    assert data["accessibility"]["can_modify"] is True
    assert data["accessibility"]["can_delete"] is True
    # No fields yet → null area
    assert data["total_area_acres"] is None


@pytest.mark.asyncio
async def test_region_detail_area_sums_fields(
    client: AsyncClient, db_session: AsyncSession, test_user, test_group
):
    """total_area_acres sums area_acres of member fields."""
    from openfmis.models.region import RegionMember

    token = await _login(client)
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Sum Farm", "group_id": str(test_group.id)},
    )
    region_id = uuid.UUID(resp.json()["id"])

    f1 = Field(
        id=uuid.uuid4(),
        name="N40",
        group_id=test_group.id,
        region_id=region_id,
        area_acres=40.0,
        version=1,
        is_current=True,
    )
    f2 = Field(
        id=uuid.uuid4(),
        name="S80",
        group_id=test_group.id,
        region_id=region_id,
        area_acres=80.5,
        version=1,
        is_current=True,
    )
    db_session.add_all([f1, f2])
    await db_session.flush()

    db_session.add(RegionMember(region_id=region_id, field_id=f1.id))
    db_session.add(RegionMember(region_id=region_id, field_id=f2.id))
    await db_session.flush()

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["field_count"] == 2
    assert data["total_area_acres"] == pytest.approx(120.5)


@pytest.mark.asyncio
async def test_region_detail_excludes_deleted_fields(
    client: AsyncClient, db_session: AsyncSession, test_user, test_group
):
    """Deleted fields excluded from total_area_acres."""
    from datetime import UTC, datetime

    from openfmis.models.region import RegionMember

    token = await _login(client)
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "Trim Farm", "group_id": str(test_group.id)},
    )
    region_id = uuid.UUID(resp.json()["id"])

    active = Field(
        id=uuid.uuid4(),
        name="Active",
        group_id=test_group.id,
        region_id=region_id,
        area_acres=50.0,
        version=1,
        is_current=True,
    )
    deleted = Field(
        id=uuid.uuid4(),
        name="Deleted",
        group_id=test_group.id,
        region_id=region_id,
        area_acres=100.0,
        version=1,
        is_current=True,
        deleted_at=datetime.now(UTC),
    )
    db_session.add_all([active, deleted])
    await db_session.flush()

    db_session.add(RegionMember(region_id=region_id, field_id=active.id))
    db_session.add(RegionMember(region_id=region_id, field_id=deleted.id))
    await db_session.flush()

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    data = resp.json()
    assert data["total_area_acres"] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_region_detail_accessibility_read_only_user(
    client: AsyncClient, db_session: AsyncSession
):
    """User with only regions.read sees can_modify=false, can_delete=false."""
    ro_group = Group(id=uuid.uuid4(), name="ReadOnlyRegGroup")
    db_session.add(ro_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=ro_group.id,
        resource_type="regions",
        resource_id=None,
        permissions={
            "regions.read": "GRANT",
            "regions.create": "GRANT",
            "regions.modify": "DENY",
            "regions.delete": "DENY",
        },
    )
    db_session.add(priv)
    await db_session.flush()

    await _make_user_in_group(db_session, ro_group, "ro_region_detail")

    # Create region as this user (has create perm)
    token = await _login(client, "ro_region_detail", "pass123")
    resp = await client.post(
        "/api/v1/regions",
        headers=_auth(token),
        json={"name": "RO Region", "group_id": str(ro_group.id)},
    )
    assert resp.status_code == 201
    region_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/regions/{region_id}", headers=_auth(token))
    assert resp.status_code == 200
    acc = resp.json()["accessibility"]
    assert acc["can_read"] is True
    assert acc["can_modify"] is False
    assert acc["can_delete"] is False


@pytest.mark.asyncio
async def test_get_total_area_acres_service(db_session: AsyncSession, test_group):
    """RegionService.get_total_area_acres sums correctly."""
    from openfmis.models.region import RegionMember

    region = Region(id=uuid.uuid4(), name="SvcArea", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()

    f1 = Field(
        id=uuid.uuid4(),
        name="F1",
        group_id=test_group.id,
        region_id=region.id,
        area_acres=25.3,
        version=1,
        is_current=True,
    )
    f2 = Field(
        id=uuid.uuid4(),
        name="F2",
        group_id=test_group.id,
        region_id=region.id,
        area_acres=74.7,
        version=1,
        is_current=True,
    )
    db_session.add_all([f1, f2])
    await db_session.flush()

    db_session.add(RegionMember(region_id=region.id, field_id=f1.id))
    db_session.add(RegionMember(region_id=region.id, field_id=f2.id))
    await db_session.flush()

    svc = RegionService(db_session)
    total = await svc.get_total_area_acres(region.id)
    assert total == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_get_total_area_acres_empty(db_session: AsyncSession, test_group):
    """Returns None for empty region."""
    region = Region(id=uuid.uuid4(), name="EmptySvc", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()

    svc = RegionService(db_session)
    assert await svc.get_total_area_acres(region.id) is None
