# Deployment Guide

## Requirements

- Python 3.12+
- PostgreSQL 14+ with PostGIS 3.3+
- ~512MB RAM minimum (more for large datasets)

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (`postgresql+asyncpg://user:pass@host:5432/dbname`) |
| `JWT_SECRET_KEY` | Secret for JWT signing and SMTP password encryption. Use a strong random value (≥32 chars). |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `GEODATA_DATABASE_URL` | (none) | Separate database for national PLSS/CLU boundary data |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Comma-separated allowed origins |
| `APP_ENV` | `development` | Environment name |
| `APP_DEBUG` | `true` | Debug mode (set `false` in production) |
| `APP_LOG_LEVEL` | `INFO` | Logging level |
| `RATE_LIMIT_RPM` | `120` | Requests per minute per IP |

## Docker

### Development

```bash
# Start PostGIS database
docker compose up -d db

# Run the app locally
source .venv/bin/activate
uvicorn openfmis.main:create_app --factory --reload
```

### Production

```bash
# Build and run
docker compose up -d

# Or build just the app image
docker build -t openfmis .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e JWT_SECRET_KEY="..." \
  openfmis
```

### docker-compose.yml

The included `docker-compose.yml` provides:
- `db` — PostGIS database (port 5432)
- `app` — OpenFMIS application (port 8000)

### Testing

```bash
# Start test database (port 5433)
docker compose -f docker-compose.test.yml up -d

# Run tests
pytest tests/ -v
```

## Database Setup

### Create Database

```sql
CREATE DATABASE openfmis;
\c openfmis
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Run Migrations

```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/openfmis"
export JWT_SECRET_KEY="your-secret"

alembic upgrade head
```

### Geodata Database (Optional)

For national PLSS/CLU boundary data, use a separate database:

```bash
export GEODATA_DATABASE_URL="postgresql+asyncpg://user:pass@rds-host:5432/geodata"
```

This is queried by the boundary proxy endpoints (`/api/v1/boundaries/*`).

### Load Reference Data

```bash
# Load PLSS data
python scripts/load_plss.py

# Load CLU data
python scripts/load_clu.py
```

## Production Considerations

### Security

- **JWT_SECRET_KEY**: Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- **APP_DEBUG**: Set to `false` in production
- **CORS_ORIGINS**: Restrict to your actual frontend domain(s)
- **HTTPS**: Run behind a reverse proxy (nginx, Caddy) with TLS termination
- **Database**: Use strong passwords, restrict network access, enable SSL

### Performance

- **Workers**: Use `gunicorn` with uvicorn workers for multi-process:
  ```bash
  gunicorn openfmis.main:create_app \
    --factory \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000
  ```
- **Rate Limiting**: The built-in rate limiter is per-process (in-memory). For multi-worker deployments, use a Redis-backed rate limiter or external rate limiting (nginx, API gateway).
- **Database Connections**: SQLAlchemy uses connection pooling by default. Tune `pool_size` and `max_overflow` in `database.py` for your workload.
- **GZip**: Enabled by default for responses ≥1000 bytes. Geospatial responses benefit significantly.

### Monitoring

- **Health checks**: `GET /api/v1/health` and `GET /api/v1/health/ready`
- **Request logging**: All requests logged to `openfmis.access` logger with method, path, status, duration, user_id, IP
- **Session audit**: Login/logout events tracked in `session_audit` table

### Backup

- **Database**: Regular pg_dump of the primary database
- **Geodata**: PLSS/CLU data can be reloaded from USDA sources if needed
- **Migrations**: Always test `alembic downgrade` before deploying new migrations

## SMTP Email Configuration

Email delivery is configured per-group via the API:

```bash
# Set SMTP config
curl -X PUT /api/v1/satshot/email-config/ \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "delivery_method": "smtp",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_username": "user@example.com",
    "smtp_password": "app-password",
    "smtp_use_tls": true,
    "smtp_from_address": "noreply@example.com"
  }'
```

SMTP passwords are encrypted at rest using Fernet (derived from JWT_SECRET_KEY via SHA-256).
