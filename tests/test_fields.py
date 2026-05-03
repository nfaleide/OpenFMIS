"""Field tests — CRUD, geometry, versioning, ACL enforcement."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege, PermissionState, UserPrivilege
from openfmis.models.region import Region
from openfmis.models.user import User
from openfmis.schemas.field import FieldCreate
from openfmis.security.password import hash_password
from openfmis.services.field import FieldService

# Sample GeoJSON — a simple square polygon in Kansas
SAMPLE_GEOJSON = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.0, 38.0],
                [-98.0, 38.01],
                [-97.99, 38.01],
                [-97.99, 38.0],
                [-98.0, 38.0],
            ]
        ]
    ],
}

SAMPLE_GEOJSON_V2 = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.0, 38.0],
                [-98.0, 38.02],
                [-97.98, 38.02],
                [-97.98, 38.0],
                [-98.0, 38.0],
            ]
        ]
    ],
}


async def _login(
    client: AsyncClient, username: str = "testuser", password: str = "testpassword123"
) -> str:
    resp = await client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Unit tests via FieldService ────────────────────────────────


@pytest.mark.asyncio
async def test_create_field_without_geometry(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(name="North 40", group_id=test_group.id, region_id=test_region.id)
    )
    assert field.name == "North 40"
    assert field.version == 1
    assert field.is_current is True
    assert field.geometry is None


@pytest.mark.asyncio
async def test_create_field_with_geometry(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(
            name="South Field",
            group_id=test_group.id,
            region_id=test_region.id,
            geometry_geojson=SAMPLE_GEOJSON,
        )
    )
    assert field.name == "South Field"
    assert field.area_acres is not None
    assert field.area_acres > 0


@pytest.mark.asyncio
async def test_update_geometry_creates_version(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    v1 = await svc.create_field(
        FieldCreate(
            name="Versioned Field",
            group_id=test_group.id,
            region_id=test_region.id,
            geometry_geojson=SAMPLE_GEOJSON,
        )
    )
    assert v1.version == 1

    v2 = await svc.update_geometry(v1.id, SAMPLE_GEOJSON_V2)
    assert v2.version == 2
    assert v2.supersedes_id == v1.id
    assert v2.is_current is True

    # Reload v1 to check it's no longer current
    v1_reloaded = await svc.get_by_id(v1.id)
    assert v1_reloaded.is_current is False


@pytest.mark.asyncio
async def test_version_history(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    v1 = await svc.create_field(
        FieldCreate(
            name="HistField",
            group_id=test_group.id,
            region_id=test_region.id,
            geometry_geojson=SAMPLE_GEOJSON,
        )
    )
    v2 = await svc.update_geometry(v1.id, SAMPLE_GEOJSON_V2)

    history = await svc.get_version_history(v2.id)
    assert len(history) == 2
    assert history[0].version == 2  # newest first
    assert history[1].version == 1


@pytest.mark.asyncio
async def test_soft_delete_field(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(name="DeleteMe", group_id=test_group.id, region_id=test_region.id)
    )
    await svc.soft_delete(field.id)

    with pytest.raises(Exception):
        await svc.get_by_id(field.id)


# ── API endpoint tests (require ACL grant) ────────────────────


@pytest.mark.asyncio
async def test_api_create_field(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "API Field",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Field"
    assert data["version"] == 1
    assert data["is_current"] is True


@pytest.mark.asyncio
async def test_api_create_field_with_geometry(
    client: AsyncClient, test_user, test_group, test_region
):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Geo Field",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
            "geometry_geojson": SAMPLE_GEOJSON,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["area_acres"] is not None
    assert data["area_acres"] > 0


@pytest.mark.asyncio
async def test_api_get_field_with_geometry(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)

    # Create
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Detail Field",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
            "geometry_geojson": SAMPLE_GEOJSON,
        },
    )
    field_id = create_resp.json()["id"]

    # Get detail
    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry_geojson"] is not None
    assert data["geometry_geojson"]["type"] == "MultiPolygon"


@pytest.mark.asyncio
async def test_api_list_fields(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)
    await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "List1", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )
    await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "List2", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )

    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_api_update_field(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "OrigName", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )
    field_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/fields/{field_id}",
        headers=_auth(token),
        json={"name": "NewName"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NewName"


@pytest.mark.asyncio
async def test_api_delete_field(client: AsyncClient, test_user, test_group, test_region):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "ToDelete", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )
    field_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 404


# ── ACL 5-state matrix tests ─────────────────────────────────


async def _make_user_in_group(
    db: AsyncSession,
    group: Group,
    username: str,
    password: str = "pass123",
    *,
    is_superuser: bool = False,
) -> User:
    """Helper to create a user belonging to a group."""
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
async def test_acl_superuser_allowed(client: AsyncClient, db_session, test_group, test_region):
    """Superusers bypass all ACL checks — no grants needed."""
    await _make_user_in_group(db_session, test_group, "su_fields", is_superuser=True)
    token = await _login(client, "su_fields", "pass123")

    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "SU Field", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )
    assert resp.status_code == 201
    field_id = resp.json()["id"]

    # Read
    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 200

    # List
    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200

    # Update
    resp = await client.patch(
        f"/api/v1/fields/{field_id}", headers=_auth(token), json={"name": "Renamed"}
    )
    assert resp.status_code == 200

    # Delete
    resp = await client.delete(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_acl_group_grant_allowed(client: AsyncClient, db_session, test_group, test_region):
    """User in a group with GRANT on fields.* can do everything."""
    await _make_user_in_group(db_session, test_group, "granted_user")
    token = await _login(client, "granted_user", "pass123")

    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Granted Field",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
    )
    assert resp.status_code == 201
    field_id = resp.json()["id"]

    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 200

    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_acl_user_deny_overrides_group_grant(
    client: AsyncClient, db_session, test_group, test_region
):
    """User-level DENY overrides group-level GRANT."""
    user = await _make_user_in_group(db_session, test_group, "denied_user")

    # User-level DENY on fields.read
    user_priv = UserPrivilege(
        id=uuid.uuid4(),
        user_id=user.id,
        resource_type="fields",
        resource_id=None,
        permissions={"fields.read": PermissionState.DENY},
    )
    db_session.add(user_priv)
    await db_session.flush()

    token = await _login(client, "denied_user", "pass123")

    # List should return empty (DENY on read)
    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Create a field as superuser so we have something to try to read
    await _make_user_in_group(db_session, test_group, "su_for_deny", is_superuser=True)
    su_token = await _login(client, "su_for_deny", "pass123")
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(su_token),
        json={"name": "Hidden", "group_id": str(test_group.id), "region_id": str(test_region.id)},
    )
    field_id = create_resp.json()["id"]

    # Get should be denied
    resp = await client.get(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_no_entry_denied(client: AsyncClient, db_session, test_region):
    """User in a group with NO permission entries → default DENY."""
    other_group = Group(id=uuid.uuid4(), name="NoPermsGroup")
    db_session.add(other_group)
    await db_session.flush()

    await _make_user_in_group(db_session, other_group, "noperm_user")
    token = await _login(client, "noperm_user", "pass123")

    # List returns empty (not 403)
    resp = await client.get("/api/v1/fields", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # Create should be denied
    region = Region(id=uuid.uuid4(), name="Other Region", group_id=other_group.id)
    db_session.add(region)
    await db_session.flush()

    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={"name": "Nope", "group_id": str(other_group.id), "region_id": str(region.id)},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_append_only_user(client: AsyncClient, db_session):
    """User with fields.create=GRANT but fields.modify=DENY can POST but not PATCH."""
    # Create a dedicated group with append-only permissions
    append_group = Group(id=uuid.uuid4(), name="AppendOnlyGroup")
    db_session.add(append_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=append_group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.create": PermissionState.GRANT,
            "fields.modify": PermissionState.DENY,
            "fields.delete": PermissionState.DENY,
        },
    )
    db_session.add(priv)
    region = Region(id=uuid.uuid4(), name="Append Region", group_id=append_group.id)
    db_session.add(region)
    await db_session.flush()

    await _make_user_in_group(db_session, append_group, "append_user")
    token = await _login(client, "append_user", "pass123")

    # Create should work
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Append Field",
            "group_id": str(append_group.id),
            "region_id": str(region.id),
        },
    )
    assert resp.status_code == 201
    field_id = resp.json()["id"]

    # PATCH should be denied (modify=DENY)
    resp = await client.patch(
        f"/api/v1/fields/{field_id}", headers=_auth(token), json={"name": "Changed"}
    )
    assert resp.status_code == 403

    # DELETE should be denied
    resp = await client.delete(f"/api/v1/fields/{field_id}", headers=_auth(token))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_modify_only_user_cannot_create(client: AsyncClient, db_session):
    """User with fields.modify=GRANT but fields.create=DENY cannot POST."""
    # Create a dedicated group with modify-only permissions
    mod_group = Group(id=uuid.uuid4(), name="ModifyOnlyGroup")
    db_session.add(mod_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=mod_group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.create": PermissionState.DENY,
            "fields.modify": PermissionState.GRANT,
            "fields.delete": PermissionState.GRANT,
        },
    )
    db_session.add(priv)
    region = Region(id=uuid.uuid4(), name="Mod Region", group_id=mod_group.id)
    db_session.add(region)
    await db_session.flush()

    await _make_user_in_group(db_session, mod_group, "modify_user")
    token = await _login(client, "modify_user", "pass123")

    # Create should be denied
    resp = await client.post(
        "/api/v1/fields",
        headers=_auth(token),
        json={
            "name": "Nope",
            "group_id": str(mod_group.id),
            "region_id": str(region.id),
        },
    )
    assert resp.status_code == 403

    # But if a field exists (created by superuser), modify should work
    await _make_user_in_group(db_session, mod_group, "su_for_mod", is_superuser=True)
    su_token = await _login(client, "su_for_mod", "pass123")
    create_resp = await client.post(
        "/api/v1/fields",
        headers=_auth(su_token),
        json={
            "name": "Editable",
            "group_id": str(mod_group.id),
            "region_id": str(region.id),
        },
    )
    field_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/fields/{field_id}", headers=_auth(token), json={"name": "Edited"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Edited"


# ── Boundary version auto-creation on geometry change ────────────────────────


@pytest.mark.asyncio
async def test_create_field_with_geometry_creates_boundary_version(
    db_session: AsyncSession, test_group, test_region
):
    """Creating a field with geometry should auto-create a FieldBoundaryVersion."""
    from openfmis.services.field_boundary_version import FieldBoundaryVersionService

    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(
            name="BV-Create Field",
            group_id=test_group.id,
            region_id=test_region.id,
            geometry_geojson=SAMPLE_GEOJSON,
        )
    )

    bv_svc = FieldBoundaryVersionService(db_session)
    versions = await bv_svc.list_by_field(field.id)
    assert len(versions) == 1
    assert versions[0].is_current is True
    assert versions[0].version == 1
    assert versions[0].source == "geometry_update"


@pytest.mark.asyncio
async def test_update_geometry_creates_boundary_version(
    db_session: AsyncSession, test_group, test_region
):
    """Updating field geometry should auto-create another FieldBoundaryVersion."""
    from openfmis.services.field_boundary_version import FieldBoundaryVersionService

    svc = FieldService(db_session)
    v1 = await svc.create_field(
        FieldCreate(
            name="BV-Update Field",
            group_id=test_group.id,
            region_id=test_region.id,
            geometry_geojson=SAMPLE_GEOJSON,
        )
    )

    v2 = await svc.update_geometry(v1.id, SAMPLE_GEOJSON_V2)

    bv_svc = FieldBoundaryVersionService(db_session)
    # The new field gets the boundary version (v2 is the new field record)
    versions = await bv_svc.list_by_field(v2.id)
    assert len(versions) >= 1
    assert versions[0].is_current is True

    # The original field also had one
    v1_versions = await bv_svc.list_by_field(v1.id)
    assert len(v1_versions) >= 1


@pytest.mark.asyncio
async def test_create_field_without_geometry_no_boundary_version(
    db_session: AsyncSession, test_group, test_region
):
    """Creating a field without geometry should NOT create a boundary version."""
    from openfmis.services.field_boundary_version import FieldBoundaryVersionService

    svc = FieldService(db_session)
    field = await svc.create_field(
        FieldCreate(
            name="No-Geom Field",
            group_id=test_group.id,
            region_id=test_region.id,
        )
    )

    bv_svc = FieldBoundaryVersionService(db_session)
    versions = await bv_svc.list_by_field(field.id)
    assert len(versions) == 0


# ── Batch rename tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_rename_service(db_session: AsyncSession, test_group, test_region):
    svc = FieldService(db_session)
    f1 = await svc.create_field(
        FieldCreate(name="OldA", group_id=test_group.id, region_id=test_region.id)
    )
    f2 = await svc.create_field(
        FieldCreate(name="OldB", group_id=test_group.id, region_id=test_region.id)
    )

    renamed = await svc.batch_rename([(f1.id, "NewA"), (f2.id, "NewB")])
    assert len(renamed) == 2

    r1 = await svc.get_by_id(f1.id)
    r2 = await svc.get_by_id(f2.id)
    assert r1.name == "NewA"
    assert r2.name == "NewB"


@pytest.mark.asyncio
async def test_batch_rename_not_found(db_session: AsyncSession):
    svc = FieldService(db_session)
    renamed = await svc.batch_rename([(uuid.uuid4(), "Ghost")])
    assert renamed == []


@pytest.mark.asyncio
async def test_api_batch_rename(
    client: AsyncClient, test_user, test_group, test_region, auth_headers
):
    # Create fields via API
    resp1 = await client.post(
        "/api/v1/fields",
        json={
            "name": "Batch1",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
        headers=auth_headers,
    )
    resp2 = await client.post(
        "/api/v1/fields",
        json={
            "name": "Batch2",
            "group_id": str(test_group.id),
            "region_id": str(test_region.id),
        },
        headers=auth_headers,
    )
    fid1 = resp1.json()["id"]
    fid2 = resp2.json()["id"]

    resp = await client.post(
        "/api/v1/fields/batch-rename",
        json={
            "renames": [
                {"field_id": fid1, "name": "Renamed1"},
                {"field_id": fid2, "name": "Renamed2"},
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["renamed"]) == 2
    assert len(data["denied"]) == 0
    assert len(data["not_found"]) == 0


@pytest.mark.asyncio
async def test_api_batch_rename_with_not_found(
    client: AsyncClient, test_user, test_group, test_region, auth_headers
):
    ghost_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/fields/batch-rename",
        json={"renames": [{"field_id": ghost_id, "name": "Ghost"}]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert ghost_id in [str(x) for x in data["not_found"]]
