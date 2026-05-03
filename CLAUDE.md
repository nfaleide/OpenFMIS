# OpenFMIS — Developer Guide

## Quick Start

```bash
# Activate venv
source .venv/bin/activate

# Run tests (requires PostGIS — use docker-compose.test.yml or local)
pytest tests/ -v

# Run linter
ruff check src/ tests/
ruff format --check src/ tests/

# Start dev server
DATABASE_URL="postgresql+asyncpg://openfmis:openfmis@localhost:5432/openfmis" \
JWT_SECRET_KEY="dev-secret-key" \
uvicorn openfmis.main:create_app --factory --host 127.0.0.1 --port 8000 --reload

# Run migrations
DATABASE_URL="postgresql+asyncpg://openfmis:openfmis@localhost:5432/openfmis" \
JWT_SECRET_KEY="dev-secret-key" \
alembic upgrade head
```

## Architecture

- **Framework**: FastAPI + SQLAlchemy 2.0 async + PostGIS + Alembic
- **Auth**: JWT + Argon2id with MD5 lazy migration from legacy system
- **ACL**: Tri-state (GRANT/ALLOW/DENY) with group hierarchy inheritance
- **Source layout**: `src/openfmis/` — models, services, api, schemas, security, core, plugin_sdk, middleware
- **206 API endpoints** across 37 routers
- **36 database models**, 25 Alembic migrations (001–025)
- **837 tests** across 30+ test files

## Key Patterns

- **Services layer**: All business logic in `services/` (50 files). Routes are thin wrappers.
- **Plugin system**: `plugin_sdk/` provides hooks, events, billing, datasets, ACL delegation. Plugins register via manifests. See `docs/plugin-guide.md`.
- **Versioning**: Fields and FieldEvents use `supersedes_id` chains with `is_current` flag.
- **Soft deletes**: Most models use `deleted_at` column; queries filter `WHERE deleted_at IS NULL`.
- **Test isolation**: Each test uses a savepoint that rolls back. No cleanup needed.
- **Middleware stack**: Request logging → Rate limiting (120 RPM) → GZip compression → CORS.
- **Geometry**: PostGIS MULTIPOLYGON with SRID 4326. ST_AsMVT for vector tiles.

## Configuration

Environment variables (see `src/openfmis/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://openfmis:openfmis@localhost:5432/openfmis` | Primary database |
| `GEODATA_DATABASE_URL` | (optional) | Separate RDS for national PLSS/CLU data |
| `JWT_SECRET_KEY` | (required) | Secret for JWT signing and SMTP password encryption |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed origins |
| `APP_ENV` | `development` | Environment name |
| `APP_DEBUG` | `true` | Debug mode |
| `APP_LOG_LEVEL` | `INFO` | Log level |
| `RATE_LIMIT_RPM` | `120` | Requests per minute per IP |

## Database

- Primary: `postgresql+asyncpg://` (PostGIS required)
- Geodata: Optional separate connection for national boundary data
- Tests: `openfmis_test` database (same server or docker-compose.test.yml on port 5433)
- 25 Alembic migrations (001–025). See `docs/migrations.md` for full chain.

## Test Commands

```bash
pytest tests/ -v                        # All tests
pytest tests/test_fields.py -v          # Single file
pytest -k "test_create_field" -v        # By name pattern
pytest tests/ -x                        # Stop on first failure
```

## Lint/Format

```bash
ruff check --fix src/ tests/    # Auto-fix lint issues
ruff format src/ tests/          # Auto-format
```

## Important Files

- `src/openfmis/main.py` — App factory, lifespan, middleware wiring, plugin registration
- `src/openfmis/api/router.py` — All route registration (37 routers, 206 endpoints)
- `src/openfmis/models/__init__.py` — Model registry (must list all models for Alembic)
- `src/openfmis/dependencies.py` — FastAPI DI: auth, ACL checks, group/field access verification
- `src/openfmis/plugin_sdk/` — Public plugin API: hooks, events, billing, datasets, ACL, manifest
- `src/openfmis/security/password.py` — Argon2id + MD5 legacy migration
- `src/openfmis/security/jwt.py` — Access + refresh token creation/validation
- `src/openfmis/services/acl.py` — Tri-state permission resolution
- `src/openfmis/services/billing.py` — Credit accounting + pricing catalog
- `src/openfmis/services/tiles.py` — MVT tile generation (fields, CLU, PLSS + plugin layers)
- `tests/conftest.py` — Fixtures (db_session, client, test_user, test_field, auth_headers)

## Adding New Features

1. **Model**: Add to `models/`, import in `models/__init__.py`
2. **Migration**: `alembic revision --autogenerate -m "description"`
3. **Schema**: Add Pydantic models to `schemas/`
4. **Service**: Business logic in `services/` — keep routes thin
5. **Route**: Add to `api/v1/`, register in `api/router.py`
6. **Tests**: Add to `tests/`, use `db_session` and `client` fixtures
7. **Docs**: Update relevant docs in `docs/`
