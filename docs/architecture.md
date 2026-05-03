# Architecture

## System Overview

OpenFMIS is a FastAPI application with an async SQLAlchemy ORM layer over PostgreSQL + PostGIS. All business logic lives in the services layer; API routes are thin wrappers that handle HTTP concerns (status codes, pagination, auth injection) and delegate to services.

```
HTTP Request
    │
    ▼
┌─────────────────────┐
│     Middleware       │  GZip → CORS → Logging → Rate Limit
└────────┬────────────┘
         ▼
┌─────────────────────┐
│   FastAPI Router     │  37 routers, 206 endpoints
│   (api/v1/*.py)      │  Auth extraction via dependencies.py
└────────┬────────────┘
         ▼
┌─────────────────────┐
│   Services Layer     │  50 service files — all business logic
│   (services/*.py)    │  Receives AsyncSession, returns models/dicts
└────────┬────────────┘
         ▼
┌─────────────────────┐
│   SQLAlchemy 2.0     │  36 ORM models, async sessions
│   + PostGIS          │  MULTIPOLYGON, MULTIPOINT, spatial indexes
└────────┬────────────┘
         ▼
┌─────────────────────┐
│   PostgreSQL         │  Primary DB + optional Geodata DB (PLSS/CLU)
└─────────────────────┘
```

## Database Schema

### Core Domain Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `users` | User accounts | username (unique), email, password_hash, is_superuser, group_id FK |
| `groups` | Tenant hierarchy | name, parent_id (self-FK for tree), settings (JSONB) |
| `user_privileges` | Per-user ACL | user_id FK, resource_type, resource_id, permissions (JSONB) |
| `group_privileges` | Per-group ACL | group_id FK, resource_type, resource_id, permissions (JSONB) |
| `token_blacklist` | Revoked JWTs | jti (unique), expires_at |
| `api_keys` | Long-lived API tokens | user_id FK, key_hash (unique), key_prefix, expires_at, revoked_at |
| `session_audit` | Login/logout trail | user_id FK, event_type, ip_address, user_agent, jti |

### Geospatial Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `fields` | Farm field boundaries | geometry (MULTIPOLYGON, SRID 4326), area_acres, group_id FK, region_id FK, supersedes_id (version chain), is_current |
| `field_boundary_versions` | Permanent geometry history | field_id FK, geometry, version, is_current, source |
| `regions` | Field grouping | name, group_id FK, is_private |
| `region_members` | Region ↔ field junction | region_id FK, field_id FK (unique pair) |
| `plss_townships` | PLSS reference data | lndkey, state, town, range_, geom (MULTIPOLYGON) |
| `plss_sections` | PLSS sections | lndkey, sectn, mtrs, geom (MULTIPOLYGON) |
| `clu` | USDA Common Land Units | state, county_fips, calcacres, geom (MULTIPOLYGON) |

### Operations Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `crop_years` | Field lifecycle periods | field_id FK, label, start_date, end_date, crop_code, tillage |
| `field_events` | Farm operations | field_id FK, event_type (9 types), crop_year_id FK, data (JSONB), supersedes_id (version chain) |
| `field_event_entries` | Event sub-entries | event_id FK, entry_type, sort_order, data (JSONB) |
| `photos` | Field/event photos | storage_url, location (POINT), object_type/object_id (polymorphic) |
| `equipment` | Farm equipment | group_id FK, name, make, model, year, equipment_type |

### Data & Analysis Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `point_datasets` | Soil samples, yield data | field_id FK, dataset_type, label, value_column, unit, soil_lab |
| `point_cleaning_log` | Data cleaning audit | dataset_id FK, rule_type, parameters (JSONB), points_removed |
| `sampling_plans` | Sample point generation | field_id FK, algorithm (5 types), status, points (MULTIPOINT), points_geojson |
| `interpolation_surfaces` | Gridded surfaces | dataset_id FK, method, cell_size_m, parameters (JSONB) |
| `prescriptions` | Variable-rate zones | field_id FK, zones (JSONB), geometry (MULTIPOLYGON), rec_model |

### Billing & Plugin Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `credit_accounts` | Credit balances | owner_type (user/group), owner_id, balance |
| `credit_ledger` | Immutable transactions | account_id FK, entry_type, amount, balance_after |
| `price_catalog` | Operation pricing | operation (unique), credit_cost, module_id |
| `plugins` | Plugin registry | slug (unique), name, version, manifest (JSONB), is_active |
| `core_datasets` | Plugin-attached data | plugin_slug, dataset_type, field_id FK, metadata (JSONB) |
| `subscriptions` | Plugin subscriptions | owner_type/id, plugin_id, status, expires_at |
| `email_configs` | Per-group email setup | group_id FK (unique), delivery_method, smtp_password_encrypted |

### Integration Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `adapt_entity_map` | ADAPT ID mapping | internal_type/id ↔ adapt_type/id |
| `sync_state` | Desktop sync tracking | user_id FK, group_id FK, client_id, last_sync_at |
| `sync_conflicts` | Sync conflict log | sync_state_id FK, entity_type, server_data/client_data (JSONB) |
| `export_links` | Shareable downloads | hash (unique), format, expires_at, download_count |
| `preferences` | User settings | user_id FK, namespace, data (JSONB) |
| `logos` | Group branding | group_id FK (unique), storage_url |

## ACL Model

OpenFMIS uses a **tri-state permission system** (GRANT / ALLOW / DENY):

```
Resolution order (first match wins):
  1. User-level privilege  →  GRANT or DENY?  →  done
  2. Group-level privilege →  GRANT or DENY?  →  done
  3. Group hierarchy walk  →  check ancestors
  4. Default               →  DENY
```

- **GRANT**: Explicit allow — overrides group DENY
- **ALLOW**: Inherited allow — can be overridden by DENY at a lower level
- **DENY**: Explicit deny — blocks access

Superusers (`is_superuser=True`) bypass all ACL checks.

### Permission Format

Permissions use `<domain>.<action>` format:
- `fields.read`, `fields.create`, `fields.modify`, `fields.delete`
- `fielddata.read`, `fielddata.append`, `fielddata.modify`
- `regions.read`, `regions.create`, `regions.modify`, `regions.delete`
- `view_financials`, `make_payments`
- `change_group_settings`, `change_object_acls`

### Group Access

Most endpoints verify the user belongs to the same group as the target resource:
- Fields have `group_id` — user must be in that group (or superuser)
- Regions, equipment, crop years inherit group from their parent field/group
- `verify_group_access()` and `verify_field_access()` dependencies enforce this

## Authentication

### JWT Flow

1. `POST /api/v1/login` — username + password → access_token + refresh_token
2. Access token: 30-min TTL, contains `sub` (user_id), `jti`, `type: "access"`
3. Refresh token: 7-day TTL, contains `sub`, `jti`, `type: "refresh"`
4. `POST /api/v1/refresh` — exchange refresh token for new token pair
5. `POST /api/v1/logout` — blacklists the access token's `jti`

### Password Security

- New passwords: Argon2id (time_cost=3, memory=64MiB, parallelism=4)
- Legacy passwords: MD5 hex detected and transparently re-hashed on login
- `needs_rehash()` flags outdated Argon2 parameters for upgrade

### API Keys

- Long-lived bearer tokens for automation/integrations
- Created per-user with optional expiry
- Stored as SHA-256 hash; prefix shown for identification
- Revocable; `last_used_at` tracked

## Middleware Stack

Applied in order (outermost first):

1. **GZip Compression** — Compress responses ≥1000 bytes
2. **CORS** — Configurable origins, credentials enabled
3. **Request Logging** — Method, path, status, duration (ms), user_id, IP → `openfmis.access` logger
4. **Rate Limiting** — Sliding window, 120 RPM per IP (configurable). Skips health checks. Returns 429 with `Retry-After` header.

## Plugin System

Plugins extend OpenFMIS without modifying core code. See [Plugin Guide](plugin-guide.md) for details.

### Registration

Plugins declare capabilities via `PluginManifest` and register at startup:
- **Tile layers** — Custom MVT layers served alongside core layers
- **Dataset types** — Custom data attached to fields via `core_datasets`
- **Export formats** — Custom export handlers
- **Charge types** — Billable operations registered in price catalog
- **Event subscriptions** — React to scene lifecycle and plugin events
- **Notification providers** — Custom notification delivery
- **PDF sections** — Custom report sections
- **Cost estimators** — Dynamic pricing logic

### Event Bus

Async pub/sub for decoupled communication:
```python
event_bus.subscribe("scene.indexed", my_handler)
await event_bus.emit("scene.indexed", {"scene_id": "S2A_123"})
```

## Versioning Pattern

Fields and FieldEvents support immutable version chains:

```
Field v1 (is_current=False)
  ↑ supersedes_id
Field v2 (is_current=False)
  ↑ supersedes_id
Field v3 (is_current=True)  ← active version
```

- Only `is_current=True` versions appear in default queries
- Version history walkable via `supersedes_id` chain
- FieldBoundaryVersions are a separate permanent history (no soft delete)

## Soft Delete Pattern

Most entities use `deleted_at` timestamp:
- `NULL` = active
- Non-null = soft-deleted
- Default queries filter `WHERE deleted_at IS NULL`
- Some entities (TokenBlacklist, SessionAudit, FieldBoundaryVersion) are permanent — no soft delete

## Testing

- **Isolation**: Each test gets a savepoint that auto-rolls back
- **Fixtures**: `db_session`, `client` (httpx AsyncClient), `test_user`, `test_field`, `auth_headers`
- **No cleanup needed**: Savepoint handles it
- **837 tests** across 30+ files covering services, API endpoints, ACL, billing, plugins, middleware
