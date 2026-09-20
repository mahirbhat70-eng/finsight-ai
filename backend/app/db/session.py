"""Async SQLAlchemy session plumbing (asyncpg driver).

Phase-1 addition: init_models() — dev path create_all. Production uses
Alembic (backend/alembic); models are the single source of truth either way.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request."""
    async with get_session_factory()() as session:
        yield session


async def init_models() -> None:
    """Dev shortcut: create_all (idempotent). Prefer Alembic in staging/prod."""
    from sqlalchemy import text
    from app.models import Base  # noqa: F401 — imports the full metadata

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None


__all__ = ["get_engine", "get_session_factory", "get_db", "init_models",
           "dispose_engine"]
