"""Photo tests — CRUD + event linking + ACL enforcement."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.models.privilege import GroupPrivilege, PermissionState
from openfmis.models.user import User
from openfmis.schemas.photo import PhotoCreate, PhotoUpdate
from openfmis.security.password import hash_password
from openfmis.services.photo import PhotoService


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
    group = Group(id=uuid.uuid4(), name="PhotoCo")
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
    await db_session.flush()
    return group


# ── Unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_photo(db_session: AsyncSession):
    svc = PhotoService(db_session)
    photo = await svc.create_photo(
        PhotoCreate(
            storage_url="gs://bucket/photos/test.jpg",
            description="Test photo",
            content_type="image/jpeg",
        )
    )
    assert photo.storage_url == "gs://bucket/photos/test.jpg"
    assert photo.description == "Test photo"


@pytest.mark.asyncio
async def test_create_photo_with_location(db_session: AsyncSession):
    svc = PhotoService(db_session)
    photo = await svc.create_photo(
        PhotoCreate(
            storage_url="gs://bucket/photos/geo.jpg",
            latitude=38.0,
            longitude=-98.0,
        )
    )
    assert photo.location is not None


@pytest.mark.asyncio
async def test_update_photo(db_session: AsyncSession):
    svc = PhotoService(db_session)
    photo = await svc.create_photo(PhotoCreate(storage_url="gs://bucket/photos/upd.jpg"))
    updated = await svc.update_photo(photo.id, PhotoUpdate(description="Updated"))
    assert updated.description == "Updated"


@pytest.mark.asyncio
async def test_soft_delete_photo(db_session: AsyncSession):
    svc = PhotoService(db_session)
    photo = await svc.create_photo(PhotoCreate(storage_url="gs://bucket/photos/del.jpg"))
    await svc.soft_delete(photo.id)
    with pytest.raises(Exception):
        await svc.get_by_id(photo.id)


@pytest.mark.asyncio
async def test_list_photos_by_object(db_session: AsyncSession):
    svc = PhotoService(db_session)
    oid = uuid.uuid4()
    await svc.create_photo(
        PhotoCreate(storage_url="gs://bucket/a.jpg", object_type="field", object_id=oid)
    )
    await svc.create_photo(
        PhotoCreate(storage_url="gs://bucket/b.jpg", object_type="field", object_id=oid)
    )
    await svc.create_photo(
        PhotoCreate(storage_url="gs://bucket/c.jpg", object_type="event", object_id=uuid.uuid4())
    )

    photos, total = await svc.list_photos(object_type="field", object_id=oid)
    assert total == 2


# ── API tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_create_photo(client: AsyncClient, test_user):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/api.jpg", "description": "API photo"},
    )
    assert resp.status_code == 201
    assert resp.json()["storage_url"] == "gs://bucket/api.jpg"


@pytest.mark.asyncio
async def test_api_get_photo(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/get.jpg"},
    )
    photo_id = create_resp.json()["id"]
    resp = await client.get(f"/api/v1/photos/{photo_id}", headers=_auth(token))
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_list_photos(client: AsyncClient, test_user):
    token = await _login(client)
    await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/l1.jpg"},
    )
    await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/l2.jpg"},
    )
    resp = await client.get("/api/v1/photos", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 2


@pytest.mark.asyncio
async def test_api_delete_photo(client: AsyncClient, test_user):
    token = await _login(client)
    create_resp = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/del.jpg"},
    )
    photo_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/v1/photos/{photo_id}", headers=_auth(token))
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
async def test_acl_read_only_cannot_upload(client: AsyncClient, db_session):
    """User with fields.read but not fields.modify cannot upload photos."""
    read_group = Group(id=uuid.uuid4(), name="PhotoReadOnlyGroup")
    db_session.add(read_group)
    await db_session.flush()

    priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=read_group.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.modify": PermissionState.DENY,
        },
    )
    db_session.add(priv)
    await db_session.flush()

    await _make_user_in_group(db_session, read_group, "photo_reader")
    token = await _login(client, "photo_reader", "pass123")

    # List should work (read=GRANT)
    resp = await client.get("/api/v1/photos", headers=_auth(token))
    assert resp.status_code == 200

    # Upload should fail (modify=DENY)
    resp = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/nope.jpg"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_no_field_perms_denied(client: AsyncClient, db_session):
    """User with no field permissions sees empty photo list and cannot upload."""
    no_perm_group = Group(id=uuid.uuid4(), name="NoFieldPermsPhotoGroup")
    db_session.add(no_perm_group)
    await db_session.flush()

    await _make_user_in_group(db_session, no_perm_group, "no_field_perm_photo")
    token = await _login(client, "no_field_perm_photo", "pass123")

    resp = await client.get("/api/v1/photos", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={"storage_url": "gs://bucket/denied.jpg"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_acl_per_field_photo_inheritance(client: AsyncClient, db_session):
    """Photos inherit per-field ACL: user with DENY on field B cannot view B's photo."""
    from openfmis.models.field import Field
    from openfmis.models.privilege import UserPrivilege
    from openfmis.models.region import Region

    # Setup: group with fields.read=GRANT
    grp = Group(id=uuid.uuid4(), name="PerFieldPhotoGroup")
    db_session.add(grp)
    await db_session.flush()

    gpriv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=grp.id,
        resource_type="fields",
        resource_id=None,
        permissions={
            "fields.read": PermissionState.GRANT,
            "fields.modify": PermissionState.GRANT,
        },
    )
    db_session.add(gpriv)
    await db_session.flush()

    region = Region(id=uuid.uuid4(), name="Photo Region", group_id=grp.id)
    db_session.add(region)
    await db_session.flush()

    # Two fields
    field_a = Field(
        id=uuid.uuid4(),
        name="Field A",
        group_id=grp.id,
        region_id=region.id,
        version=1,
        is_current=True,
    )
    field_b = Field(
        id=uuid.uuid4(),
        name="Field B",
        group_id=grp.id,
        region_id=region.id,
        version=1,
        is_current=True,
    )
    db_session.add_all([field_a, field_b])
    await db_session.flush()

    user = await _make_user_in_group(db_session, grp, "per_field_photo_user")

    # User has DENY on field_b specifically
    upriv = UserPrivilege(
        id=uuid.uuid4(),
        user_id=user.id,
        resource_type="fields",
        resource_id=field_b.id,
        permissions={"fields.read": PermissionState.DENY},
    )
    db_session.add(upriv)
    await db_session.flush()

    token = await _login(client, "per_field_photo_user", "pass123")

    # Create photo on field_a (allowed)
    resp_a = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={
            "storage_url": "gs://bucket/field_a.jpg",
            "object_type": "field",
            "object_id": str(field_a.id),
        },
    )
    assert resp_a.status_code == 201
    photo_a_id = resp_a.json()["id"]

    # Create photo on field_b (allowed because modify is not per-field denied)
    resp_b = await client.post(
        "/api/v1/photos",
        headers=_auth(token),
        json={
            "storage_url": "gs://bucket/field_b.jpg",
            "object_type": "field",
            "object_id": str(field_b.id),
        },
    )
    assert resp_b.status_code == 201
    photo_b_id = resp_b.json()["id"]

    # Can GET photo_a (field_a read=GRANT via group)
    resp = await client.get(f"/api/v1/photos/{photo_a_id}", headers=_auth(token))
    assert resp.status_code == 200

    # Cannot GET photo_b (field_b read=DENY via user privilege)
    resp = await client.get(f"/api/v1/photos/{photo_b_id}", headers=_auth(token))
    assert resp.status_code == 403
