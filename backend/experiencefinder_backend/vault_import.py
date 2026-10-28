"""Import destination and experience Markdown cards from the vault into the database.

The vault remains the source of truth. Database rows with ``origin="vault"`` are a
derived, replaceable projection used by the API.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from experiencefinder_backend.db import get_session_factory
from experiencefinder_backend.models import Destination, Guide

logger = logging.getLogger(__name__)


@dataclass
class TableImportReport:
    """Counters for one imported database table."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0


@dataclass
class ImportReport:
    """Result of a complete destination and guide vault import."""

    destinations: TableImportReport = field(default_factory=TableImportReport)
    guides: TableImportReport = field(default_factory=TableImportReport)
    errors: list[str] = field(default_factory=list)


def parse_card(path: Path) -> tuple[dict, str]:
    """Read a Markdown card and split its YAML frontmatter from its body."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return {}, text

    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip("\r\n") == "---"
        ),
        None,
    )
    if closing_index is None:
        raise ValueError("frontmatter is missing its closing delimiter")

    loaded = yaml.safe_load("".join(lines[1:closing_index])) or {}
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter must contain a YAML mapping")
    body = "".join(lines[closing_index + 1 :]).strip()
    return loaded, body


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _title(frontmatter: dict, slug: str) -> str:
    return _optional_text(frontmatter.get("title")) or slug


def _tags(frontmatter: dict) -> list[str]:
    value = frontmatter.get("tags", [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("frontmatter 'tags' must be a list")
    return [item if isinstance(item, str) else str(item) for item in value]


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _sources(frontmatter: dict) -> str | None:
    value = _optional_text(frontmatter.get("sources"))
    return value or None


def _visibility(frontmatter: dict) -> str:
    return _optional_text(frontmatter.get("visibility", "public")) or "public"


def _destination_values(path: Path) -> dict[str, Any]:
    frontmatter, body = parse_card(path)
    slug = path.stem
    return {
        "slug": slug,
        "title": _title(frontmatter, slug),
        "paese": _optional_text(frontmatter.get("paese")),
        "stagione_ideale": _optional_text(frontmatter.get("stagione-ideale")),
        "budget_medio": _optional_text(frontmatter.get("budget-medio")),
        "giorni_consigliati": _optional_text(frontmatter.get("giorni-consigliati")),
        "coverage": _optional_text(frontmatter.get("coverage")),
        "tags": _tags(frontmatter),
        "created": _date(frontmatter.get("created")),
        "updated": _date(frontmatter.get("updated")),
        "sources": _sources(frontmatter),
        "body": body,
        "source_path": f"vault/wiki/destinazioni/{slug}.md",
        "visibility": _visibility(frontmatter),
        "origin": "vault",
    }


def _guide_values(path: Path) -> dict[str, Any]:
    frontmatter, body = parse_card(path)
    slug = path.stem
    return {
        "slug": slug,
        "section": "esperienze",
        "title": _title(frontmatter, slug),
        "coverage": _optional_text(frontmatter.get("coverage")),
        "tags": _tags(frontmatter),
        "created": _date(frontmatter.get("created")),
        "updated": _date(frontmatter.get("updated")),
        "sources": _sources(frontmatter),
        "body": body,
        "source_path": f"vault/wiki/esperienze/{slug}.md",
        "visibility": _visibility(frontmatter),
        "origin": "vault",
    }


async def _upsert_destinations(
    session: AsyncSession,
    values: list[dict[str, Any]],
    vault_slugs: set[str],
    report: TableImportReport,
) -> None:
    existing = {
        row.slug: row for row in await session.scalars(select(Destination))
    }
    for item in values:
        row = existing.get(item["slug"])
        if row is None:
            session.add(Destination(**item))
            report.created += 1
        elif all(getattr(row, key) == value for key, value in item.items()):
            report.unchanged += 1
        else:
            for key, value in item.items():
                setattr(row, key, value)
            report.updated += 1

    for slug, row in existing.items():
        if row.origin == "vault" and slug not in vault_slugs:
            await session.delete(row)
            report.deleted += 1


async def _upsert_guides(
    session: AsyncSession,
    values: list[dict[str, Any]],
    vault_slugs: set[str],
    report: TableImportReport,
) -> None:
    existing = {row.slug: row for row in await session.scalars(select(Guide))}
    for item in values:
        row = existing.get(item["slug"])
        if row is None:
            session.add(Guide(**item))
            report.created += 1
        elif all(getattr(row, key) == value for key, value in item.items()):
            report.unchanged += 1
        else:
            for key, value in item.items():
                setattr(row, key, value)
            report.updated += 1

    for slug, row in existing.items():
        if row.origin == "vault" and slug not in vault_slugs:
            await session.delete(row)
            report.deleted += 1


def _read_cards(
    directory: Path,
    mapper: Callable[[Path], dict[str, Any]],
    report: ImportReport,
) -> tuple[list[dict[str, Any]], set[str]]:
    values: list[dict[str, Any]] = []
    paths = sorted(directory.glob("*.md"))
    vault_slugs = {path.stem for path in paths}
    for path in paths:
        try:
            values.append(mapper(path))
        except Exception as exc:  # noqa: BLE001 - one bad card must not stop the import
            error = f"{path}: {exc}"
            logger.warning("Skipping vault card %s: %s", path, exc)
            report.errors.append(error)
    return values, vault_slugs


async def import_vault(session: AsyncSession, vault_dir: Path) -> ImportReport:
    """Synchronize destination and experience cards into the database."""
    report = ImportReport()
    wiki_dir = vault_dir / "wiki"
    destination_values, destination_slugs = _read_cards(
        wiki_dir / "destinazioni", _destination_values, report
    )
    guide_values, guide_slugs = _read_cards(
        wiki_dir / "esperienze", _guide_values, report
    )

    await _upsert_destinations(
        session,
        destination_values,
        destination_slugs,
        report.destinations,
    )
    await _upsert_guides(session, guide_values, guide_slugs, report.guides)
    await session.commit()
    return report


def default_vault_dir() -> Path:
    """Return the configured vault directory or the node's default vault path."""
    configured = os.getenv("VAULT_DIR")
    if configured:
        return Path(configured)
    node_root = Path(__file__).resolve().parents[2]
    return node_root / "vault"


async def _run_cli(vault_dir: Path) -> ImportReport:
    async with get_session_factory()() as session:
        return await import_vault(session, vault_dir)


def main() -> int:
    """Run the vault importer from the command line."""
    parser = argparse.ArgumentParser(description="Import the Markdown vault into the database")
    parser.add_argument("--vault", type=Path, default=default_vault_dir())
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(_run_cli(args.vault))
    logger.info("Vault import completed: %s", report)
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
