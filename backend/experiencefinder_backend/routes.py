"""Domain API routes: destinations and guides.

Ported from the monolithic Travelers repo (`/destinations`, `/guides`) — see
`brain/architettura/decisioni.md`. `Trip`/`/trips` stayed with the Travel node.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from suite_backend_core import get_settings

from experiencefinder_backend.db import get_session
from experiencefinder_backend.models import Destination, Guide
from experiencefinder_backend.schemas import DestinationDetail, DestinationSummary, GuideOut

router = APIRouter(prefix="/api")

# Sections this node currently owns (only "esperienze" migrated so far; other
# Travelers guide sections — logistica/documenti/budget — stayed with Travel).
GUIDE_SECTIONS = {"esperienze"}


@router.get("/health")
async def api_health(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """DB-aware health: same shape as core ``/health`` plus a ``database`` key.

    Unlike the static core route, this one actually touches the database, so a
    green status means the API routes can serve real traffic (a stale image or
    broken DB connection previously left ``/health`` green while every
    ``/api/*`` route failed).
    """
    service = get_settings().app_name
    try:
        await session.execute(select(1))
    except Exception:  # noqa: BLE001 — any DB failure means unhealthy
        return JSONResponse(
            status_code=503,
            content={"status": "error", "service": service, "database": "error"},
        )
    return JSONResponse(
        content={"status": "ok", "service": service, "database": "ok"}
    )


@router.get("/destinations", response_model=list[DestinationSummary])
async def list_destinations(
    session: AsyncSession = Depends(get_session),
) -> list[Destination]:
    result = await session.scalars(select(Destination).order_by(Destination.title))
    return list(result)


@router.get("/destinations/{destination_id}", response_model=DestinationDetail)
async def get_destination(
    destination_id: str, session: AsyncSession = Depends(get_session)
) -> Destination:
    query = (
        select(Destination).where(Destination.id == int(destination_id))
        if destination_id.isdigit()
        else select(Destination).where(Destination.slug == destination_id)
    )
    destination = await session.scalar(query)
    if destination is None:
        raise HTTPException(status_code=404, detail="Destination not found")
    return destination


@router.get("/guides", response_model=list[GuideOut])
async def list_guides(
    section: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[Guide]:
    query = select(Guide).order_by(Guide.section, Guide.title)
    if section is not None:
        if section not in GUIDE_SECTIONS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown section '{section}'. Valid: {sorted(GUIDE_SECTIONS)}",
            )
        query = query.where(Guide.section == section)
    result = await session.scalars(query)
    return list(result)
