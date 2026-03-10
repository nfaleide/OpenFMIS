# OpenFMIS — Developer Guide

## Quick Start

```bash
cd openfmis
# Activate venv
source .venv/bin/activate

# Run tests (requires local PostgreSQL with PostGIS on port 5432)
pytest tests/ -v

# Run linter
ruff check src/ tests/
ruff format --check src/ tests/

# Start dev server
DATABASE_URL="postgresql+asyncpg://faleideairbook@localhost:5432/openfmis" \
JWT_SECRET_KEY="dev-secret-key" \
uvicorn openfmis.main:create_app --factory --host 127.0.0.1 --port 8000 --reload

# Run migrations
DATABASE_URL="postgresql+asyncpg://faleideairbook@localhost:5432/openfmis" \
JWT_SECRET_KEY="dev-secret-key" \
alembic upgrade head
```

## Architecture

- **Framework**: FastAPI + SQLAlchemy 2.0 async + PostGIS + Alembic
- **Auth**: JWT + Argon2id with MD5 lazy migration from legacy system
- **ACL**: Tri-state (GRANT/ALLOW/DENY) with group hierarchy inheritance
- **Source layout**: `src/openfmis/` — models, services, api, schemas, security, core

## Key Patterns

- **Services layer**: All business logic in `services/`. Routes are thin wrappers.
- **Band math**: Safe AST-based formula evaluation in `services/band_math.py`. No eval().
- **Band registry**: `services/band_registry.py` normalizes band names across Sentinel-2, Sentinel-1, Landsat, custom uploads.
- **Plugin system**: `core/plugin_registry.py` + `core/events.py` event bus.
- **Test isolation**: Each test uses a savepoint that rolls back. No cleanup needed.

## Database

- Local dev: `postgresql+asyncpg://faleideairbook@localhost:5432/openfmis`
- Tests: `openfmis_test` database on same server
- Docker test: `docker-compose.test.yml` runs PostGIS on port 5433
- 12 Alembic migrations (001–012)

## Test Commands

```bash
pytest tests/ -v                    # All tests
pytest tests/test_band_math.py -v   # Single file
pytest -k "test_ndvi" -v            # By name pattern
```

## Lint/Format

```bash
ruff check --fix src/ tests/    # Auto-fix lint issues
ruff format src/ tests/          # Auto-format
```

## Important Files

- `src/openfmis/main.py` — App factory, lifespan, plugin registration
- `src/openfmis/api/router.py` — All route registration (172 operations)
- `src/openfmis/models/__init__.py` — Model registry (must list all models for Alembic)
- `src/openfmis/services/band_math.py` — Formula engine, 29 builtin indices
- `src/openfmis/services/band_registry.py` — Collection profiles
- `tests/conftest.py` — Fixtures (db_session, client, test_user)
