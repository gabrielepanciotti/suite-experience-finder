"""Test-wide setup: point DATABASE_URL at a throwaway sqlite file before any
module under test imports the app/db module (db.py builds its engine lazily,
but we still want a single, stable URL for the whole test session).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP_DB = Path(tempfile.gettempdir()) / "experiencefinder_backend_test.db"
if _TMP_DB.exists():
    _TMP_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["VAULT_IMPORT_ON_STARTUP"] = "0"
