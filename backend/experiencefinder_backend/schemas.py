"""Pydantic response schemas for the ExperienceFinder API."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DestinationSummary(_OrmModel):
    id: int
    slug: str
    title: str
    paese: str | None
    stagione_ideale: str | None
    budget_medio: str | None
    giorni_consigliati: str | None
    coverage: str | None
    tags: list[str]


class DestinationDetail(DestinationSummary):
    created: date | None
    updated: date | None
    sources: str | None
    body: str
    source_path: str


class GuideOut(_OrmModel):
    id: int
    slug: str
    section: str
    title: str
    coverage: str | None
    tags: list[str]
    created: date | None
    updated: date | None
    body: str
    source_path: str
