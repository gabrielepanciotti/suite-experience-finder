"""Smoke tests for the ExperienceFinder API: health + destinations/guides routes."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from suite_backend_core import Base

from experiencefinder_backend.app import app
from experiencefinder_backend.db import get_engine, get_session_factory
from experiencefinder_backend.models import Destination, Guide


@pytest_asyncio.fixture
async def client():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_client(client):
    session_factory = get_session_factory()
    async with session_factory() as session:
        session.add(
            Destination(
                slug="giappone",
                title="Giappone",
                paese="Giappone",
                source_path="vault/wiki/destinazioni/giappone.md",
                visibility="public",
            )
        )
        session.add(
            Guide(
                slug="avventura-trekking",
                section="esperienze",
                title="Avventura / Trekking",
                source_path="vault/wiki/esperienze/avventura-trekking.md",
                visibility="public",
            )
        )
        await session.commit()
    return client


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_api_health_db_aware(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "service" in body


@pytest.mark.asyncio
async def test_api_health_db_down(client, monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("db unreachable")

    from sqlalchemy.ext.asyncio import AsyncSession

    monkeypatch.setattr(AsyncSession, "execute", _boom)
    resp = await client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert body["database"] == "error"


@pytest.mark.asyncio
async def test_list_destinations_empty(client):
    resp = await client.get("/api/destinations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_destinations_seeded(seeded_client):
    resp = await seeded_client.get("/api/destinations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "giappone"


@pytest.mark.asyncio
async def test_get_destination_by_slug(seeded_client):
    resp = await seeded_client.get("/api/destinations/giappone")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Giappone"


@pytest.mark.asyncio
async def test_get_destination_not_found(client):
    resp = await client.get("/api/destinations/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_guides_filtered_by_section(seeded_client):
    resp = await seeded_client.get("/api/guides", params={"section": "esperienze"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "avventura-trekking"


@pytest.mark.asyncio
async def test_list_guides_unknown_section(client):
    resp = await client.get("/api/guides", params={"section": "logistica"})
    assert resp.status_code == 422
