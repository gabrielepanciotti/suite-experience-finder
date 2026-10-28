"""Async engine/session wiring for the ExperienceFinder API.

Engine and session factory are built lazily (on first use) rather than at
import time, so importing this module — or the FastAPI app — never requires
``DATABASE_URL`` to be set unless a route actually touches the database (e.g.
the ``/health`` route does not). This also lets tests set ``DATABASE_URL``
in a conftest before the first DB-touching request.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from suite_backend_core import (
    build_database_url,
    get_settings,
    make_engine,
    make_session_factory,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_engine(build_database_url(get_settings()))
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = make_session_factory(get_engine())
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session
