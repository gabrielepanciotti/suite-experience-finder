"""Integration tests for the Markdown vault importer."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
from experiencefinder_backend.app import app
from experiencefinder_backend.db import get_engine, get_session_factory
from experiencefinder_backend.models import Destination, Guide
from experiencefinder_backend.vault_import import default_vault_dir, import_vault
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from suite_backend_core import Base

DESTINATION_GIAPPONE = """---
type: destinazione
title: "Giappone"
tags: [asia, city-break-culturale, 2026]
created: 2026-06-02
updated: "2026-06-03"
sources: ""
coverage: high
paese: "Giappone"
stagione-ideale: "primavera e autunno"
budget-medio: 150
giorni-consigliati: "14-21"
---

# Giappone

Templi, città e gastronomia.
"""

DESTINATION_ISLANDA = """---
type: destinazione
title: "Islanda"
tags: [natura, on-the-road]
created: 2026-06-02
updated: 2026-06-02
sources: "https://example.test/islanda"
coverage: medium
paese: "Islanda"
stagione-ideale: "estate"
budget-medio: "200-250 €/giorno"
giorni-consigliati: 10
---

# Islanda

Vulcani, ghiacciai e cascate.
"""

GUIDE_RELAX = """---
type: guida
title: "Relax / Mare"
tags: [esperienza, relax]
created: 2026-06-02
updated: 2026-06-02
sources: ""
coverage: high
---

# Relax / Mare

Una base fissa e poco attrito logistico.
"""


def _write_mini_vault(tmp_path: Path) -> Path:
    vault_dir = tmp_path / "vault"
    destinations_dir = vault_dir / "wiki" / "destinazioni"
    experiences_dir = vault_dir / "wiki" / "esperienze"
    destinations_dir.mkdir(parents=True)
    experiences_dir.mkdir(parents=True)
    (destinations_dir / "giappone.md").write_text(
        DESTINATION_GIAPPONE, encoding="utf-8"
    )
    (destinations_dir / "islanda.md").write_text(
        DESTINATION_ISLANDA, encoding="utf-8"
    )
    (experiences_dir / "relax-mare.md").write_text(
        GUIDE_RELAX, encoding="utf-8"
    )
    return vault_dir


@pytest_asyncio.fixture
async def database():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield get_session_factory()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_first_import_maps_fields_and_second_import_is_unchanged(
    database, tmp_path
):
    vault_dir = _write_mini_vault(tmp_path)

    async with database() as session:
        first = await import_vault(session, vault_dir)

    assert first.destinations.created == 2
    assert first.guides.created == 1
    assert first.errors == []

    async with database() as session:
        destination = await session.scalar(
            select(Destination).where(Destination.slug == "giappone")
        )
        guide = await session.scalar(select(Guide).where(Guide.slug == "relax-mare"))

    assert destination is not None
    assert destination.stagione_ideale == "primavera e autunno"
    assert destination.budget_medio == "150"
    assert destination.tags == ["asia", "city-break-culturale", "2026"]
    assert destination.created == date(2026, 6, 2)
    assert destination.updated == date(2026, 6, 3)
    assert destination.sources is None
    assert destination.source_path == "vault/wiki/destinazioni/giappone.md"
    assert destination.origin == "vault"
    assert guide is not None
    assert guide.section == "esperienze"
    assert guide.sources is None
    assert guide.source_path == "vault/wiki/esperienze/relax-mare.md"
    assert guide.origin == "vault"

    async with database() as session:
        second = await import_vault(session, vault_dir)
        destination_count = await session.scalar(
            select(func.count()).select_from(Destination)
        )
        guide_count = await session.scalar(select(func.count()).select_from(Guide))

    assert second.destinations.unchanged == 2
    assert second.destinations.updated == 0
    assert second.guides.unchanged == 1
    assert second.guides.updated == 0
    assert destination_count == 2
    assert guide_count == 1


@pytest.mark.asyncio
async def test_changed_file_updates_existing_row(database, tmp_path):
    vault_dir = _write_mini_vault(tmp_path)
    async with database() as session:
        await import_vault(session, vault_dir)

    giappone = vault_dir / "wiki" / "destinazioni" / "giappone.md"
    giappone.write_text(
        DESTINATION_GIAPPONE.replace('title: "Giappone"', 'title: "Giappone nuovo"'),
        encoding="utf-8",
    )

    async with database() as session:
        report = await import_vault(session, vault_dir)
        destination = await session.scalar(
            select(Destination).where(Destination.slug == "giappone")
        )

    assert report.destinations.updated == 1
    assert report.destinations.unchanged == 1
    assert destination is not None
    assert destination.title == "Giappone nuovo"


@pytest.mark.asyncio
async def test_removed_vault_row_is_deleted_but_non_vault_row_survives(
    database, tmp_path
):
    vault_dir = _write_mini_vault(tmp_path)
    async with database() as session:
        await import_vault(session, vault_dir)
        session.add(
            Destination(
                slug="manuale",
                title="Manuale",
                source_path="manual",
                visibility="private",
                origin=None,
            )
        )
        await session.commit()

    (vault_dir / "wiki" / "destinazioni" / "islanda.md").unlink()

    async with database() as session:
        report = await import_vault(session, vault_dir)
        slugs = set(await session.scalars(select(Destination.slug)))

    assert report.destinations.deleted == 1
    assert slugs == {"giappone", "manuale"}


@pytest.mark.asyncio
async def test_broken_yaml_is_reported_without_stopping_other_files(
    database, tmp_path
):
    vault_dir = _write_mini_vault(tmp_path)
    broken = vault_dir / "wiki" / "destinazioni" / "rotta.md"
    broken.write_text("---\ntags: [broken\n---\nBody\n", encoding="utf-8")

    async with database() as session:
        report = await import_vault(session, vault_dir)
        destination_count = await session.scalar(
            select(func.count()).select_from(Destination)
        )
        guide_count = await session.scalar(select(func.count()).select_from(Guide))

    assert len(report.errors) == 1
    assert "rotta.md" in report.errors[0]
    assert destination_count == 2
    assert guide_count == 1


@pytest.mark.asyncio
async def test_imported_rows_are_returned_by_api(database, tmp_path):
    vault_dir = _write_mini_vault(tmp_path)
    async with database() as session:
        await import_vault(session, vault_dir)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        destinations_response = await client.get("/api/destinations")
        guides_response = await client.get("/api/guides")

    assert destinations_response.status_code == 200
    assert len(destinations_response.json()) == 2
    assert guides_response.status_code == 200
    assert len(guides_response.json()) == 1


@pytest.mark.asyncio
async def test_real_repository_vault_imports_expected_rows(database):
    async with database() as session:
        report = await import_vault(session, default_vault_dir())

    assert report.destinations.created == 5
    assert report.guides.created == 5
    assert report.errors == []
