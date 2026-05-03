# OpenFMIS

**Open Field Management Information System** — a modern, async Python backend for precision agriculture data management.

OpenFMIS provides the core platform for managing farm fields, boundaries, crop operations, soil sampling, prescriptions, billing, and more. It is designed as a plugin-extensible system where domain-specific functionality (imagery analytics, marketplace integrations, etc.) can be added without modifying the core.

## Features

- **Field Management** — Versioned MULTIPOLYGON boundaries with geometry operations (union, clip, buffer, intersect)
- **Crop Operations** — 9 event types (planting, harvest, scouting, soil testing, tillage, etc.) with versioning and sub-entries
- **Sampling Plans** — 5 algorithms (random, grid, clustered, W-curve, SSUS) with MODUS export
- **Prescriptions** — Variable-rate zones with interpolation surfaces and recommendation models
- **Point Data** — Yield monitor, soil sample, and as-applied data ingestion with cleaning pipelines
- **PLSS/CLU** — Public Land Survey System and Common Land Unit boundary reference data
- **MVT Tiles** — Server-side Mapbox Vector Tiles for fields, CLU, and PLSS layers
- **Import/Export** — GeoJSON, Shapefile, KML, CSV, ISOXML, SST, MODUS formats
- **Billing** — Credit-based accounting with ledger, price catalog, and plugin charge types
- **Plugin System** — Hook registries, event bus, dataset attachment, billing helpers, ACL delegation
- **ACL** — Tri-state (GRANT/ALLOW/DENY) permissions with group hierarchy inheritance
- **Auth** — JWT + Argon2id with MD5 lazy migration, API keys, session audit
- **Sync** — Bidirectional delta sync for desktop/QGIS clients with conflict resolution
- **ADAPT** — Entity mapping for ADAPT framework interoperability
- **Subscriptions** — Generic plugin subscription lifecycle management

## Quick Start

```bash
# Start PostGIS
docker compose up -d db

# Create virtualenv and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Set environment
export DATABASE_URL="postgresql+asyncpg://openfmis:openfmis@localhost:5432/openfmis"
export JWT_SECRET_KEY="change-me-in-production"

# Run migrations
alembic upgrade head

# Start dev server
uvicorn openfmis.main:create_app --factory --host 127.0.0.1 --port 8000 --reload

# Run tests
docker compose -f docker-compose.test.yml up -d
pytest tests/ -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Application                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │  Routing  │  │Middleware│  │   Auth   │  │ Static │  │
│  │ 37 routers│  │ Log/Rate │  │ JWT/ACL  │  │  HTML  │  │
│  │ 206 endpts│  │ GZip/CORS│  │ Argon2id │  │        │  │
│  └────┬─────┘  └──────────┘  └──────────┘  └────────┘  │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │              Services Layer (50 files)             │   │
│  │  Field, Region, CropYear, FieldEvent, Sampling,   │   │
│  │  Billing, ACL, Sync, PointDataset, Prescription,  │   │
│  │  Import/Export, Tiles, PLSS, CLU, Equipment ...    │   │
│  └────┬─────────────────────────────────────────────┘   │
│       │                                                  │
│  ┌────▼─────────────────────────────────────────────┐   │
│  │           Plugin SDK (hooks, events, billing)      │   │
│  │  register_tile_layer, register_export_format,      │   │
│  │  event_bus, record_charge, attach_dataset, ...     │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │     SQLAlchemy 2.0 Async + PostGIS + Alembic      │   │
│  │     36 models, 25 migrations, JSONB, geometry      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

- **Framework**: FastAPI + SQLAlchemy 2.0 async + PostGIS + Alembic
- **Auth**: JWT (access + refresh) + Argon2id + MD5 lazy migration
- **ACL**: Tri-state (GRANT/ALLOW/DENY) with user → group → hierarchy resolution
- **Validation**: Pydantic v2 request/response models
- **Testing**: pytest + anyio, savepoint isolation per test (no cleanup needed)
- **Linting**: ruff (check + format)

## Project Structure

```
src/openfmis/
├── api/
│   ├── router.py          # All route registration (37 routers)
│   └── v1/               # Route handlers (thin wrappers over services)
│       ├── auth.py, users.py, groups.py, acl.py
│       ├── fields.py, regions.py, crop_years.py
│       ├── field_events.py, geometry.py
│       ├── sampling.py, prescriptions.py
│       ├── point_datasets.py, point_ingestion.py
│       ├── billing.py, tiles.py, plugins.py
│       ├── import_.py, export_.py
│       ├── plss.py, clu.py, equipment.py
│       ├── photos.py, preferences.py, logos.py
│       ├── boundary_versions.py, boundary_proxy.py
│       ├── sync.py, adapt_map.py, subscriptions.py
│       ├── api_keys.py, highlights.py, reference.py
│       ├── datasets.py, email_config.py
│       └── ...
├── models/                # SQLAlchemy ORM models (36 models)
├── schemas/               # Pydantic request/response models
├── services/              # Business logic (50 service files)
├── security/              # JWT, password hashing, permission constants
├── middleware/             # Logging, rate limiting, compression, CORS
├── core/                  # Plugin registry, event bus
├── plugin_sdk/            # Public plugin API surface
├── config.py              # Settings (env-based)
├── database.py            # Engine + session factory
├── dependencies.py        # FastAPI DI (auth, ACL, access checks)
├── exceptions.py          # Custom exceptions
├── main.py                # App factory
└── static/                # Dashboard HTML
migrations/
├── env.py
└── versions/              # 001–025 Alembic migrations
tests/                     # 837 tests across 30+ files
```

## Documentation

- **[Architecture](docs/architecture.md)** — System design, database schema, ACL model, middleware
- **[API Reference](docs/api-reference.md)** — All 206 endpoints with methods, paths, auth requirements
- **[Plugin Guide](docs/plugin-guide.md)** — Building plugins with hooks, events, billing, datasets
- **[Migrations](docs/migrations.md)** — Migration chain (001–025) with table descriptions
- **[Deployment](docs/deployment.md)** — Docker, environment variables, production configuration

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL + PostGIS |
| Migrations | Alembic |
| Auth | JWT (PyJWT) + Argon2id (argon2-cffi) |
| Validation | Pydantic v2 |
| Testing | pytest + anyio + httpx |
| Linting | ruff |
| Geo formats | Shapefile (fiona), GeoJSON, KML, WKT |
| Vector tiles | ST_AsMVT (PostGIS native) |

## License

Proprietary — all rights reserved.
