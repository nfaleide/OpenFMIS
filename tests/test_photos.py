"""Photo tests — CRUD + event linking."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.group import Group
from openfmis.schemas.photo import PhotoCreate, PhotoUpdate
from openfmis.services.photo import PhotoService


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
    group = Group(id=uuid.uuid4(), name="PhotoCo")
    db_session.add(group)
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
        "/api/v1/photos", headers=_auth(token), json={"storage_url": "gs://bucket/l1.jpg"}
    )
    await client.post(
        "/api/v1/photos", headers=_auth(token), json={"storage_url": "gs://bucket/l2.jpg"}
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
