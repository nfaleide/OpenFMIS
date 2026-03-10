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
async def test_user(db_session: AsyncSession):
    """Create a test user with known credentials."""
    from openfmis.models.user import User

    user = User(
        id=uuid.uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("testpassword123"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.flush()
    return user


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
