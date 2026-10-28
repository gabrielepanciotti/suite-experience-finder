"""SQLAlchemy models for the ExperienceFinder node.

Ported from the monolithic `Travelers` repo (see `brain/architettura/decisioni.md`
for the split rationale): `Destination` (vault/wiki/destinazioni) and `Guide`
(vault/wiki/esperienze, plus other guide sections owned by this node in the
future). `Trip` stayed behind in the Travel node's own migration.

Registered on `suite_backend_core.Base` — picked up automatically by
`alembic revision --autogenerate` via ../database/env.py.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from suite_backend_core import Base

# JSONB on Postgres (prod); falls back to plain JSON on sqlite (tests), which
# has no native JSONB type.
_TagsType = JSONB().with_variant(JSON(), "sqlite")


class Destination(Base):
    """A destination sheet from vault/wiki/destinazioni/."""

    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    paese: Mapped[str | None] = mapped_column(String(255))
    stagione_ideale: Mapped[str | None] = mapped_column(Text)
    budget_medio: Mapped[str | None] = mapped_column(String(255))
    giorni_consigliati: Mapped[str | None] = mapped_column(String(100))
    coverage: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(_TagsType, default=list)
    created: Mapped[date | None] = mapped_column(Date)
    updated: Mapped[date | None] = mapped_column(Date)
    sources: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    source_path: Mapped[str] = mapped_column(String(500))
    visibility: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="private", index=True
    )
    origin: Mapped[str | None] = mapped_column(String(10))


class Guide(Base):
    """A how-to / reference page from esperienze (and future guide sections)."""

    __tablename__ = "guides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    section: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(500))
    coverage: Mapped[str | None] = mapped_column(String(10))
    tags: Mapped[list[str]] = mapped_column(_TagsType, default=list)
    created: Mapped[date | None] = mapped_column(Date)
    updated: Mapped[date | None] = mapped_column(Date)
    sources: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="")
    source_path: Mapped[str] = mapped_column(String(500))
    visibility: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="private", index=True
    )
    origin: Mapped[str | None] = mapped_column(String(10))
