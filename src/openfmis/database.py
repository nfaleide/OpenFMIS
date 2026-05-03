"""Async SQLAlchemy engine, session factory, and FastAPI dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from openfmis.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an async session, auto-closes."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Geodata engine (CLU/PLSS on shared RDS) ──────────────────

_geodata_url = settings.GEODATA_DATABASE_URL or settings.DATABASE_URL

geodata_engine = create_async_engine(
    _geodata_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

geodata_session_factory = async_sessionmaker(
    geodata_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_geodata_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session to the geodata (CLU/PLSS) database."""
    async with geodata_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
