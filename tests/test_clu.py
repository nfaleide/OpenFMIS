"""CLU service and API tests — uses fixture data, not production load."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.clu import CLU
from openfmis.models.group import Group
from openfmis.models.user import User
from openfmis.schemas.field import FieldCreate
from openfmis.security.password import hash_password
from openfmis.services.clu import CLUService
from openfmis.services.field import FieldService

# A Kansas CLU polygon
CLU_WKT = (
    "SRID=4326;MULTIPOLYGON (((-98.05 38.0, -98.0 38.0, -98.0 38.05, -98.05 38.05, -98.05 38.0)))"
)

# A field polygon overlapping the CLU
FIELD_MP = {
    "type": "MultiPolygon",
    "coordinates": [
        [
            [
                [-98.04, 38.01],
                [-98.01, 38.01],
                [-98.01, 38.04],
                [-98.04, 38.04],
                [-98.04, 38.01],
            ]
        ]
    ],
}


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="cluuser",
        email="clu@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="CLU User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_group(db_session: AsyncSession) -> Group:
    group = Group(id=uuid.uuid4(), name="CLUTestFarm")
    db_session.add(group)
    await db_session.flush()
    return group


@pytest.fixture
async def sample_clu(db_session: AsyncSession) -> CLU:
    clu = CLU(state="KS", county_fips="KS020", calcacres=37.5)
    db_session.add(clu)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE clu SET geom = ST_GeomFromEWKT(:wkt) WHERE id = :id"),
        {"wkt": CLU_WKT, "id": clu.id},
    )
    await db_session.flush()
    return clu


@pytest.fixture
async def test_field(db_session: AsyncSession, test_group: Group, test_user: User):
    svc = FieldService(db_session)
    return await svc.create_field(
        FieldCreate(name="CLU Test Field", group_id=test_group.id, geometry_geojson=FIELD_MP),
        created_by=test_user.id,
    )


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "cluuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── CLUService unit tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_clus_at_point(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    results = await svc.get_clus_at_point(lon=-98.025, lat=38.025)
    assert len(results) >= 1
    assert results[0]["state"] == "KS"
    assert results[0]["calcacres"] == pytest.approx(37.5)


@pytest.mark.asyncio
async def test_get_clus_at_point_miss(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    results = await svc.get_clus_at_point(lon=-120.0, lat=47.0)
    assert results == []


@pytest.mark.asyncio
async def test_get_clus_by_county(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    items, total = await svc.get_clus_by_county("KS", "KS020")
    assert total >= 1
    assert items[0]["county_fips"] == "KS020"


@pytest.mark.asyncio
async def test_get_clus_by_county_empty(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    items, total = await svc.get_clus_by_county("TX", "TX999")
    assert total == 0
    assert items == []


@pytest.mark.asyncio
async def test_get_clus_intersecting_geometry(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    results = await svc.get_clus_intersecting_geometry(FIELD_MP)
    assert len(results) >= 1
    assert results[0]["state"] == "KS"


@pytest.mark.asyncio
async def test_get_clus_for_field(db_session: AsyncSession, sample_clu: CLU, test_field):
    svc = CLUService(db_session)
    results = await svc.get_clus_for_field(test_field.id)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_get_clus_for_field_no_geometry(
    db_session: AsyncSession, test_group: Group, test_user: User
):
    """Field with no geometry should return empty list."""
    svc_field = FieldService(db_session)
    field = await svc_field.create_field(
        FieldCreate(name="No Geom", group_id=test_group.id),
        created_by=test_user.id,
    )
    svc = CLUService(db_session)
    results = await svc.get_clus_for_field(field.id)
    assert results == []


@pytest.mark.asyncio
async def test_get_available_states(db_session: AsyncSession, sample_clu: CLU):
    svc = CLUService(db_session)
    states = await svc.get_available_states()
    assert "KS" in states


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_clu_at_point(client: AsyncClient, test_user: User, sample_clu: CLU):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/clu/at-point?lon=-98.025&lat=38.025",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["state"] == "KS"


@pytest.mark.asyncio
async def test_api_clu_by_county(client: AsyncClient, test_user: User, sample_clu: CLU):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/clu/county/KS/KS020",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["county_fips"] == "KS020"


@pytest.mark.asyncio
async def test_api_clu_intersecting(client: AsyncClient, test_user: User, sample_clu: CLU):
    token = await _login(client)
    resp = await client.post(
        "/api/v1/clu/intersecting",
        headers={"Authorization": f"Bearer {token}"},
        json=FIELD_MP,
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_clu_for_field(client: AsyncClient, test_user: User, sample_clu: CLU, test_field):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/clu/fields/{test_field.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_clu_states(client: AsyncClient, test_user: User, sample_clu: CLU):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/clu/states",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "KS" in resp.json()


@pytest.mark.asyncio
async def test_api_clu_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/clu/at-point?lon=-98.0&lat=38.0")
    assert resp.status_code == 401
