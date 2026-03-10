# OpenFMIS

Open Field Management Information System — modern FastAPI backend replacing the legacy PHP system.

## Quick Start

```bash
# Start PostGIS
docker compose up -d db

# Install (editable + dev deps)
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start dev server
uvicorn openfmis.main:create_app --factory --reload

# Run tests
docker compose -f docker-compose.test.yml up -d
pytest tests/ -v
```

## Architecture

- **FastAPI** — async HTTP framework
- **SQLAlchemy 2.0** — async ORM with asyncpg
- **PostGIS** — spatial database
- **Alembic** — schema migrations
- **JWT + Argon2id** — authentication
- **Pydantic v2** — request/response validation
