"""Test fixtures — async DB, test client, user factories.

Uses a connection-level transaction with savepoints so each test
runs in isolation and rolls back on completion.
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Set test env BEFORE importing app code — respect existing env vars (e.g. CI)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://faleideairbook@localhost:5432/openfmis_test",
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "false")

from openfmis.database import get_db  # noqa: E402
from openfmis.main import create_app  # noqa: E402
from openfmis.models import Base  # noqa: E402
from openfmis.security.password import hash_password  # noqa: E402

TEST_DATABASE_URL = os.environ["DATABASE_URL"]
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.drop_all)
        # Drop orphaned enum types left behind by drop_all (tables gone, types remain)
        for enum_name in ("sampling_algorithm_enum", "sampling_plan_status_enum"):
            await conn.execute(text(f"DROP TYPE IF EXISTS {enum_name}"))
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test session using a savepoint for rollback isolation."""
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        # Use nested savepoints so session.commit() doesn't close the outer txn
        _nested = await conn.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def restart_savepoint(sync_session, transaction):
            if transaction.nested and not transaction._parent.nested:
                sync_session.begin_nested()

        yield session

        await session.close()
        await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async test client with DB session override."""
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_group):
    """Create a test user with known credentials, belonging to test_group."""
    from openfmis.models.user import User

    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        group_id=test_group.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user) -> dict[str, str]:
    """Login as test_user and return Authorization headers."""
    resp = await client.post(
        "/api/v1/login",
        json={"username": "testuser", "password": "testpassword123"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_group(db_session: AsyncSession):
    """Create a test group with full field permissions."""
    from openfmis.models.group import Group
    from openfmis.models.privilege import GroupPrivilege

    group = Group(id=uuid.uuid4(), name="FarmCo")
    db_session.add(group)
    await db_session.flush()

    # Grant full field permissions so API tests work with ACL enforcement
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
    # Grant full region permissions
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
    # Grant full fielddata permissions
    fielddata_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="fielddata",
        resource_id=None,
        permissions={
            "fielddata.read": "GRANT",
            "fielddata.append": "GRANT",
            "fielddata.modify": "GRANT",
        },
    )
    db_session.add(fielddata_priv)
    # Grant group admin permissions (equipment CRUD etc.)
    group_admin_priv = GroupPrivilege(
        id=uuid.uuid4(),
        group_id=group.id,
        resource_type="groups",
        resource_id=None,
        permissions={
            "change_group_settings": "GRANT",
            "change_object_acls": "GRANT",
        },
    )
    db_session.add(group_admin_priv)
    await db_session.flush()
    return group


@pytest_asyncio.fixture
async def test_region(db_session: AsyncSession, test_group):
    """Create a test region (farm)."""
    from openfmis.models.region import Region

    region = Region(id=uuid.uuid4(), name="Home Farm", group_id=test_group.id)
    db_session.add(region)
    await db_session.flush()
    return region


@pytest_asyncio.fixture
async def test_field(db_session: AsyncSession, test_group, test_region):
    """Create a test field with a simple square geometry for spatial tests."""
    from openfmis.models.field import Field

    wkt = (
        "SRID=4326;MULTIPOLYGON((("
        "-97.0 40.0, -97.009 40.0, -97.009 40.009, -97.0 40.009, -97.0 40.0"
        ")))"
    )
    field = Field(
        id=uuid.uuid4(),
        name="Test Field",
        group_id=test_group.id,
        region_id=test_region.id,
        version=1,
        is_current=True,
        geometry=wkt,
    )
    db_session.add(field)
    await db_session.flush()
    return field


@pytest_asyncio.fixture
async def test_user_md5(db_session: AsyncSession):
    """Create a test user with a legacy MD5 hash."""
    import hashlib

    from openfmis.models.user import User

    md5_hash = hashlib.md5(b"legacypass").hexdigest()
    user = User(
        id=uuid.uuid4(),
        username="legacyuser",
        email="legacy@example.com",
        password_hash=md5_hash,
        full_name="Legacy User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def inactive_user(db_session: AsyncSession):
    """Create an inactive test user."""
    from openfmis.models.user import User

    user = User(
        id=uuid.uuid4(),
        username="inactiveuser",
        email="inactive@example.com",
        password_hash=hash_password("password123"),
        full_name="Inactive User",
        is_active=False,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user
