"""PLSS service and API tests — uses fixture data, not production load."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.plss import PLSSSection, PLSSTownship
from openfmis.models.user import User
from openfmis.security.password import hash_password
from openfmis.services.plss import PLSSService

# A real Kansas township polygon (small, for testing)
TOWNSHIP_WKT = (
    "SRID=4326;MULTIPOLYGON (((-98.1 38.0, -98.0 38.0, -98.0 38.1, -98.1 38.1, -98.1 38.0)))"
)
SECTION_WKT = (
    "SRID=4326;MULTIPOLYGON (((-98.05 38.0, -98.0 38.0, -98.0 38.05, -98.05 38.05, -98.05 38.0)))"
)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="plssuser",
        email="plss@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="PLSS User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def sample_township(db_session: AsyncSession) -> PLSSTownship:
    twn = PLSSTownship(
        gid=99001,
        lndkey="KS06T0020S0010W",
        state="KS",
        town=2,
        twndir="S",
        range_=1,
        rngdir="W",
        label="2S 1W",
        source="BLM",
        fips_c="20001",
    )
    db_session.add(twn)
    await db_session.flush()
    # Set geometry via raw SQL (geoalchemy2 WKT insert)
    await db_session.execute(
        text("UPDATE plss_townships SET geom = ST_GeomFromEWKT(:wkt) WHERE id = :id"),
        {"wkt": TOWNSHIP_WKT, "id": twn.id},
    )
    await db_session.flush()
    return twn


@pytest.fixture
async def sample_section(db_session: AsyncSession, sample_township: PLSSTownship) -> PLSSSection:
    sec = PLSSSection(
        gid=99001,
        lndkey="KS06T0020S0010W",
        sectn=14,
        sectionkey="014",
        label="14",
        mtrs="KS06T0020S0010W014",
        source="BLM",
        fips_c="20001",
    )
    db_session.add(sec)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE plss_sections SET geom = ST_GeomFromEWKT(:wkt) WHERE id = :id"),
        {"wkt": SECTION_WKT, "id": sec.id},
    )
    await db_session.flush()
    return sec


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/login", json={"username": "plssuser", "password": "testpassword123"}
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ── PLSSService unit tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_townships_by_state(db_session: AsyncSession, sample_township: PLSSTownship):
    svc = PLSSService(db_session)
    results = await svc.search_townships(state="KS")
    assert len(results) >= 1
    assert any(t["state"] == "KS" for t in results)


@pytest.mark.asyncio
async def test_search_townships_by_label(db_session: AsyncSession, sample_township: PLSSTownship):
    svc = PLSSService(db_session)
    results = await svc.search_townships(q="2S 1W")
    assert len(results) >= 1
    assert results[0]["label"] == "2S 1W"


@pytest.mark.asyncio
async def test_get_township_by_id(db_session: AsyncSession, sample_township: PLSSTownship):
    svc = PLSSService(db_session)
    result = await svc.get_township(sample_township.id)
    assert result is not None
    assert result["lndkey"] == "KS06T0020S0010W"
    assert result["state"] == "KS"


@pytest.mark.asyncio
async def test_get_township_not_found(db_session: AsyncSession):
    svc = PLSSService(db_session)
    result = await svc.get_township(999999)
    assert result is None


@pytest.mark.asyncio
async def test_get_sections_for_township(
    db_session: AsyncSession, sample_township: PLSSTownship, sample_section: PLSSSection
):
    svc = PLSSService(db_session)
    sections = await svc.get_sections_for_township("KS06T0020S0010W")
    assert len(sections) >= 1
    assert sections[0]["lndkey"].startswith("KS06T0020S0010W")


@pytest.mark.asyncio
async def test_search_sections_by_mtrs(db_session: AsyncSession, sample_section: PLSSSection):
    svc = PLSSService(db_session)
    results = await svc.search_sections(mtrs="KS06T0020S0010W014")
    assert len(results) >= 1
    assert results[0]["mtrs"] == "KS06T0020S0010W014"


@pytest.mark.asyncio
async def test_search_sections_by_fips(db_session: AsyncSession, sample_section: PLSSSection):
    svc = PLSSService(db_session)
    results = await svc.search_sections(fips_c="20001")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_find_sections_at_point(db_session: AsyncSession, sample_section: PLSSSection):
    # Point inside the section polygon
    svc = PLSSService(db_session)
    results = await svc.find_sections_at_point(lon=-98.025, lat=38.025)
    assert len(results) >= 1
    assert results[0]["mtrs"] == "KS06T0020S0010W014"


@pytest.mark.asyncio
async def test_find_sections_at_point_miss(db_session: AsyncSession, sample_section: PLSSSection):
    # Point far outside polygon
    svc = PLSSService(db_session)
    results = await svc.find_sections_at_point(lon=-120.0, lat=47.0)
    assert results == []


@pytest.mark.asyncio
async def test_find_townships_at_point(db_session: AsyncSession, sample_township: PLSSTownship):
    svc = PLSSService(db_session)
    results = await svc.find_townships_at_point(lon=-98.05, lat=38.05)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_get_available_states(db_session: AsyncSession, sample_township: PLSSTownship):
    svc = PLSSService(db_session)
    states = await svc.get_available_states()
    assert "KS" in states


# ── API endpoint tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_search_townships(
    client: AsyncClient, test_user: User, sample_township: PLSSTownship
):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/plss/townships?state=KS",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_api_get_township(
    client: AsyncClient, test_user: User, sample_township: PLSSTownship
):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/plss/townships/{sample_township.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "KS"


@pytest.mark.asyncio
async def test_api_get_township_not_found(client: AsyncClient, test_user: User):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/plss/townships/999999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_get_sections_for_township(
    client: AsyncClient, test_user: User, sample_township: PLSSTownship, sample_section: PLSSSection
):
    token = await _login(client)
    resp = await client.get(
        f"/api/v1/plss/townships/{sample_township.id}/sections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_search_sections(
    client: AsyncClient, test_user: User, sample_section: PLSSSection
):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/plss/sections?fips_c=20001",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_api_plss_at_point(
    client: AsyncClient, test_user: User, sample_township: PLSSTownship, sample_section: PLSSSection
):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/plss/at-point?lon=-98.025&lat=38.025",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "townships" in data
    assert "sections" in data
    assert len(data["sections"]) >= 1


@pytest.mark.asyncio
async def test_api_plss_states(client: AsyncClient, test_user: User, sample_township: PLSSTownship):
    token = await _login(client)
    resp = await client.get(
        "/api/v1/plss/states",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "KS" in resp.json()


@pytest.mark.asyncio
async def test_api_plss_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/plss/townships?state=KS")
    assert resp.status_code == 401
