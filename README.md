# ExperienceFinder

ExperienceFinder is an open-source travel discovery service that keeps curated destinations, activity guides, and regional radar notes in Markdown, imports them into a database, and exposes them through a read-only FastAPI API.

## Features

- Markdown vault for destinations, travel experiences, and radar notes
- Async FastAPI API for destinations and guides
- Idempotent vault importer with Alembic migrations
- Utilities to ingest saved reels and maintain radar/place pools

## Requirements

- Python 3.13
- Node.js 20 and npm
- PostgreSQL 16 for the application (the Python tests use SQLite)
- The Life framework checked out next to this repository; it supplies the `suite_core`, `suite_backend_core`, and `@suite/design-system` packages

## Quickstart

Clone this repository and the Life framework as sibling directories, then copy the example configuration:

```sh
git clone <repository-url> experience-finder
git clone <life-framework-url> Life
cd experience-finder
cp .env.example .env
```

For a native backend run, install its dependencies and the framework packages, then start Uvicorn:

```sh
python -m pip install -r backend/requirements.txt -r tools/requirements.txt
python -m pip install ../Life/packages/shared ../Life/packages/backend-core
PYTHONPATH=backend uvicorn experiencefinder_backend.app:app --reload --port 10020
```

In a second terminal, run the frontend:

```sh
cd frontend
npm ci
npm run dev
```

Alternatively, prepare the framework vendor artifacts with `bash deploy/prebuild.sh` and start the public example stack with `docker compose --env-file .env -f deploy/docker-compose.example.yml up --build`.

## Tests

With the framework checked out as `../Life`:

```sh
PYTHONPATH=backend:. pytest backend/tests tools/tests
cd frontend && npm ci && npm test && npm run build
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST_PORT` | Host port for PostgreSQL in local Compose use |
| `DATABASE_URL` | Complete async database connection URL |
| `VAULT_DIR` | Markdown vault directory |
| `VAULT_IMPORT_ON_STARTUP` | Enables startup vault import when not `0` |
| `VITE_BACKEND_PROXY_TARGET` | API target for the Vite development proxy |

## License

MIT — see [LICENSE](LICENSE).
