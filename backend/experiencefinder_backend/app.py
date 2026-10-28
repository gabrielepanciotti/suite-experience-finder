import logging
import os

from suite_backend_core import create_app

from experiencefinder_backend.db import get_session_factory
from experiencefinder_backend.routes import router as domain_router
from experiencefinder_backend.vault_import import default_vault_dir, import_vault

logger = logging.getLogger(__name__)

app = create_app()

# `create_app` registers a static `/api/health` (and `/health` alias) that
# always answers 200 — it lied green while every DB-backed `/api/*` route
# failed. Drop the static `/api/health` so the DB-aware one in `routes.py`
# takes its place; `/health` stays as a cheap liveness-only alias.
app.router.routes = [
    route
    for route in app.router.routes
    if getattr(route, "path", None) != "/api/health"
]

app.include_router(domain_router)


async def _import_vault_on_startup() -> None:
    if os.getenv("VAULT_IMPORT_ON_STARTUP", "1") == "0":
        return

    vault_dir = default_vault_dir()
    if not vault_dir.is_dir() or not (vault_dir / "wiki").is_dir():
        logger.info("Vault directory not found at %s; skipping startup import", vault_dir)
        return

    try:
        async with get_session_factory()() as session:
            report = await import_vault(session, vault_dir)
        logger.info("Startup vault import completed: %s", report)
    except Exception:  # noqa: BLE001 - an import failure must not prevent startup
        logger.exception("Startup vault import failed")


app.router.add_event_handler("startup", _import_vault_on_startup)
