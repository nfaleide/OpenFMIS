"""Satshot service and API tests.

STAC HTTP calls and rasterio COG reads are mocked — no network or S3 required.
"""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.schemas.satshot import JobCreate, ZoneCreate, ZoneUpdate
from openfmis.security.password import hash_password
from openfmis.services.analysis import AnalysisService, ZoneService
from openfmis.services.band_math import evaluate as evaluate_formula
from openfmis.services.image_extraction import _result_stats
from openfmis.services.scene_discovery import SceneDiscoveryService

# ── Fixtures ──────────────────────────────────────────────────────────────────

FIELD_MP = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.05, 38.0],
                [-98.0, 38.0],
                [-98.0, 38.05],
                [-98.05, 38.05],
                [-98.05, 38.0],
            ]
        ]
    ],
}

FAKE_SCENE_ID = "S2B_13TDE_20240815_0_L2A"

FAKE_STAC_ITEM = {
    "id": FAKE_SCENE_ID,
    "collection": "sentinel-2-l2a",
    "bbox": [-99.0, 37.0, -97.0, 39.0],
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-99, 37], [-97, 37], [-97, 39], [-99, 39], [-99, 37]]],
    },
    "properties": {
        "datetime": "2024-08-15T12:00:00Z",
        "eo:cloud_cover": 5.2,
        "platform": "sentinel-2b",
    },
    "assets": {
        "red": {"href": "s3://sentinel-cogs/fake/B04.tif", "type": "image/tiff"},
        "nir": {"href": "s3://sentinel-cogs/fake/B08.tif", "type": "image/tiff"},
        "green": {"href": "s3://sentinel-cogs/fake/B03.tif", "type": "image/tiff"},
        "blue": {"href": "s3://sentinel-cogs/fake/B02.tif", "type": "image/tiff"},
        "rededge1": {"href": "s3://sentinel-cogs/fake/B05.tif", "type": "image/tiff"},
    },
}


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="satshotuser",
        email="satshot@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Satshot User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="SatshotFarm")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def test_field(db_session: AsyncSession, test_group: Group, test_user: User) -> Field:
    from sqlalchemy import text

    field = Field(
        id=uuid.uuid4(),
        name="Satshot Field",
        group_id=test_group.id,
        created_by=test_user.id,
        is_current=True,
        version=1,
    )
    db_session.add(field)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE fields SET geometry = ST_GeomFromGeoJSON(:g) WHERE id = :id"),
        {"g": json.dumps(FIELD_MP), "id": field.id},
    )
    await db_session.flush()
    return field


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "satshotuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── Index computation unit tests ──────────────────────────────────────────────


def test_compute_ndvi():
    nir = np.array([[0.8, 0.6], [0.4, 0.2]], dtype=float)
    red = np.array([[0.1, 0.2], [0.3, 0.1]], dtype=float)
    result = evaluate_formula("(nir - red) / (nir + red)", {"nir": nir, "red": red})
    expected = (nir - red) / (nir + red)
    np.testing.assert_allclose(result, expected)


def test_compute_ndwi():
    green = np.array([[0.3, 0.4]], dtype=float)
    nir = np.array([[0.6, 0.5]], dtype=float)
    result = evaluate_formula("(green - nir) / (green + nir)", {"green": green, "nir": nir})
    expected = (green - nir) / (green + nir)
    np.testing.assert_allclose(result, expected)


def test_compute_evi():
    nir = np.array([[0.8]], dtype=float)
    red = np.array([[0.1]], dtype=float)
    blue = np.array([[0.05]], dtype=float)
    result = evaluate_formula(
        "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)",
        {"nir": nir, "red": red, "blue": blue},
    )
    assert result.shape == (1, 1)
    assert np.isfinite(result[0, 0])


def test_compute_savi():
    nir = np.array([[0.7, 0.5]], dtype=float)
    red = np.array([[0.1, 0.2]], dtype=float)
    result = evaluate_formula("1.5 * (nir - red) / (nir + red + 0.5)", {"nir": nir, "red": red})
    assert result.shape == (1, 2)


def test_result_stats_normal():
    arr = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    stats = _result_stats(arr)
    assert stats["pixel_count"] == 5
    assert stats["valid_pixel_count"] == 5
    assert stats["nodata_fraction"] == 0.0
    assert abs(stats["mean"] - 0.5) < 0.01


def test_result_stats_with_nan():
    arr = np.array([0.5, np.nan, 0.3, np.nan])
    stats = _result_stats(arr)
    assert stats["pixel_count"] == 4
    assert stats["valid_pixel_count"] == 2
    assert stats["nodata_fraction"] == 0.5


def test_result_stats_all_nan():
    arr = np.full(10, np.nan)
    stats = _result_stats(arr)
    assert stats["mean"] is None
    assert stats["valid_pixel_count"] == 0
    assert stats["nodata_fraction"] == 1.0


# ── SceneDiscoveryService unit tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_scene(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)
    record = await svc.cache_scene(FAKE_STAC_ITEM)
    assert record.scene_id == FAKE_SCENE_ID
    assert record.cloud_cover == pytest.approx(5.2)
    assert "red" in record.assets
    assert record.acquired_at.year == 2024


@pytest.mark.asyncio
async def test_cache_scene_idempotent(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)
    r1 = await svc.cache_scene(FAKE_STAC_ITEM)
    r2 = await svc.cache_scene(FAKE_STAC_ITEM)
    assert r1.id == r2.id


@pytest.mark.asyncio
async def test_search_scenes_mocked(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)

    mock_response = MagicMock()
    mock_response.json.return_value = {"features": [FAKE_STAC_ITEM]}
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("openfmis.services.scene_discovery.httpx.AsyncClient", return_value=mock_http):
        results = await svc.search_scenes(
            geometry=FIELD_MP,
            date_from=datetime(2024, 1, 1, tzinfo=UTC),
            date_to=datetime(2024, 12, 31, tzinfo=UTC),
            cloud_cover_max=30.0,
        )
    assert len(results) == 1
    assert results[0]["scene_id"] == FAKE_SCENE_ID
    assert results[0]["cloud_cover"] == pytest.approx(5.2)


@pytest.mark.asyncio
async def test_get_scene_by_id_cached(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)
    await svc.cache_scene(FAKE_STAC_ITEM)
    scene = await svc.get_scene_by_id(FAKE_SCENE_ID)
    assert scene is not None
    assert scene["scene_id"] == FAKE_SCENE_ID


@pytest.mark.asyncio
async def test_get_scene_by_id_not_found(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("openfmis.services.scene_discovery.httpx.AsyncClient", return_value=mock_http):
        scene = await svc.get_scene_by_id("nonexistent-scene-id")
    assert scene is None


@pytest.mark.asyncio
async def test_list_cached_scenes(db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)
    await svc.cache_scene(FAKE_STAC_ITEM)
    scenes = await svc.list_cached_scenes()
    assert any(s["scene_id"] == FAKE_SCENE_ID for s in scenes)


# ── ZoneService unit tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_zone(db_session: AsyncSession, test_field: Field, test_user: User):
    svc = ZoneService(db_session)
    zone = await svc.create_zone(
        test_field.id,
        ZoneCreate(name="North Quarter", geometry_geojson=FIELD_MP),
        created_by=test_user.id,
    )
    assert zone.name == "North Quarter"
    assert zone.field_id == test_field.id


@pytest.mark.asyncio
async def test_list_zones(db_session: AsyncSession, test_field: Field, test_user: User):
    svc = ZoneService(db_session)
    await svc.create_zone(test_field.id, ZoneCreate(name="Z1"), created_by=test_user.id)
    await svc.create_zone(test_field.id, ZoneCreate(name="Z2"), created_by=test_user.id)
    zones = await svc.list_zones(test_field.id)
    names = [z["name"] for z in zones]
    assert "Z1" in names and "Z2" in names


@pytest.mark.asyncio
async def test_update_zone(db_session: AsyncSession, test_field: Field, test_user: User):
    svc = ZoneService(db_session)
    zone = await svc.create_zone(
        test_field.id, ZoneCreate(name="Old Name"), created_by=test_user.id
    )
    updated = await svc.update_zone(zone.id, ZoneUpdate(name="New Name"))
    assert updated.name == "New Name"


@pytest.mark.asyncio
async def test_delete_zone(db_session: AsyncSession, test_field: Field, test_user: User):
    svc = ZoneService(db_session)
    zone = await svc.create_zone(
        test_field.id, ZoneCreate(name="To Delete"), created_by=test_user.id
    )
    await svc.delete_zone(zone.id)
    assert await svc.get_zone(zone.id) is None


# ── AnalysisService unit tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_job_creates_pending(
    db_session: AsyncSession, test_field: Field, test_user: User
):
    svc = AnalysisService(db_session)
    await SceneDiscoveryService(db_session).cache_scene(FAKE_STAC_ITEM)

    with patch(
        "openfmis.services.analysis.asyncio.create_task", side_effect=lambda coro: coro.close()
    ):
        job = await svc.submit_job(
            JobCreate(field_id=test_field.id, scene_id=FAKE_SCENE_ID, index_type="ndvi"),
            created_by=test_user.id,
        )
    assert job.status == "pending"
    assert job.index_type == "ndvi"
    assert job.field_id == test_field.id


@pytest.mark.asyncio
async def test_submit_job_field_not_found(db_session: AsyncSession, test_user: User):
    from openfmis.services.analysis import FieldNotFoundError

    svc = AnalysisService(db_session)
    with pytest.raises(FieldNotFoundError):
        await svc.submit_job(
            JobCreate(field_id=uuid.uuid4(), scene_id=FAKE_SCENE_ID, index_type="ndvi"),
            created_by=test_user.id,
        )


@pytest.mark.asyncio
async def test_list_jobs(db_session: AsyncSession, test_field: Field, test_user: User):
    svc = AnalysisService(db_session)
    await SceneDiscoveryService(db_session).cache_scene(FAKE_STAC_ITEM)
    with patch(
        "openfmis.services.analysis.asyncio.create_task", side_effect=lambda coro: coro.close()
    ):
        await svc.submit_job(
            JobCreate(field_id=test_field.id, scene_id=FAKE_SCENE_ID, index_type="ndvi"),
            created_by=test_user.id,
        )
    jobs, total = await svc.list_jobs(field_id=test_field.id)
    assert total >= 1


# ── API endpoint tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_search_scenes(client: AsyncClient, test_user: User):
    token = await _login(client)

    mock_response = MagicMock()
    mock_response.json.return_value = {"features": [FAKE_STAC_ITEM]}
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("openfmis.services.scene_discovery.httpx.AsyncClient", return_value=mock_http):
        resp = await client.post(
            "/api/v1/satshot/scenes/search",
            json={
                "geometry": FIELD_MP,
                "date_from": "2024-01-01T00:00:00Z",
                "date_to": "2024-12-31T00:00:00Z",
                "cloud_cover_max": 30.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["scene_id"] == FAKE_SCENE_ID


@pytest.mark.asyncio
async def test_api_get_scene_cached(client: AsyncClient, test_user: User, db_session: AsyncSession):
    svc = SceneDiscoveryService(db_session)
    await svc.cache_scene(FAKE_STAC_ITEM)
    await db_session.flush()

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/satshot/scenes/{FAKE_SCENE_ID}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["scene_id"] == FAKE_SCENE_ID


@pytest.mark.asyncio
async def test_api_get_scene_not_found(client: AsyncClient, test_user: User):
    token = await _login(client)

    mock_resp = MagicMock()
    mock_resp.status_code = 404

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("openfmis.services.scene_discovery.httpx.AsyncClient", return_value=mock_http):
        resp = await client.get(
            "/api/v1/satshot/scenes/totally-fake-scene-xyz",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_create_zone(client: AsyncClient, test_user: User, test_field: Field):
    token = await _login(client)
    resp = await client.post(
        f"/api/v1/satshot/fields/{test_field.id}/zones",
        json={"name": "North Zone", "geometry_geojson": FIELD_MP},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "North Zone"


@pytest.mark.asyncio
async def test_api_list_zones(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    svc = ZoneService(db_session)
    await svc.create_zone(test_field.id, ZoneCreate(name="Zone A"), created_by=test_user.id)
    await db_session.flush()

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/satshot/fields/{test_field.id}/zones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert any(z["name"] == "Zone A" for z in resp.json())


@pytest.mark.asyncio
async def test_api_update_zone(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    svc = ZoneService(db_session)
    zone = await svc.create_zone(test_field.id, ZoneCreate(name="Old"), created_by=test_user.id)
    await db_session.flush()

    token = await _login(client)
    resp = await client.patch(
        f"/api/v1/satshot/zones/{zone.id}",
        json={"name": "Updated"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


@pytest.mark.asyncio
async def test_api_delete_zone(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    svc = ZoneService(db_session)
    zone = await svc.create_zone(test_field.id, ZoneCreate(name="Gone"), created_by=test_user.id)
    await db_session.flush()

    token = await _login(client)
    resp = await client.delete(
        f"/api/v1/satshot/zones/{zone.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_api_submit_job(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    await SceneDiscoveryService(db_session).cache_scene(FAKE_STAC_ITEM)
    await db_session.flush()

    token = await _login(client)
    with patch(
        "openfmis.services.analysis.asyncio.create_task", side_effect=lambda coro: coro.close()
    ):
        resp = await client.post(
            "/api/v1/satshot/jobs",
            json={"field_id": str(test_field.id), "scene_id": FAKE_SCENE_ID, "index_type": "ndvi"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "pending"
    assert data["index_type"] == "ndvi"


@pytest.mark.asyncio
async def test_api_list_jobs(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    await SceneDiscoveryService(db_session).cache_scene(FAKE_STAC_ITEM)
    svc = AnalysisService(db_session)
    with patch(
        "openfmis.services.analysis.asyncio.create_task", side_effect=lambda coro: coro.close()
    ):
        await svc.submit_job(
            JobCreate(field_id=test_field.id, scene_id=FAKE_SCENE_ID, index_type="ndwi"),
            created_by=test_user.id,
        )
    await db_session.flush()

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/satshot/jobs?field_id={test_field.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_get_job(
    client: AsyncClient, test_user: User, test_field: Field, db_session: AsyncSession
):
    await SceneDiscoveryService(db_session).cache_scene(FAKE_STAC_ITEM)
    svc = AnalysisService(db_session)
    with patch(
        "openfmis.services.analysis.asyncio.create_task", side_effect=lambda coro: coro.close()
    ):
        job = await svc.submit_job(
            JobCreate(field_id=test_field.id, scene_id=FAKE_SCENE_ID, index_type="savi"),
            created_by=test_user.id,
        )
    await db_session.flush()

    token = await _login(client)
    resp = await client.get(
        f"/api/v1/satshot/jobs/{job.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["index_type"] == "savi"


@pytest.mark.asyncio
async def test_api_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/satshot/scenes/cached")
    assert resp.status_code == 401
