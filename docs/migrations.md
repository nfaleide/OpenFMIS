# Migration Chain

OpenFMIS uses Alembic for database migrations. The chain runs from 001 to 025 with linear dependencies.

## Running Migrations

```bash
# Apply all migrations
alembic upgrade head

# Apply to specific revision
alembic upgrade 015

# Rollback one step
alembic downgrade -1

# Rollback to specific revision
alembic downgrade 008

# Show current revision
alembic current

# Show migration history
alembic history
```

## Migration Chain

| Rev | Name | Description | Tables |
|-----|------|-------------|--------|
| 001 | `initial_auth` | Users, groups, privileges, token blacklist | `groups`, `users`, `user_privileges`, `group_privileges`, `token_blacklist` |
| 002 | `fields` | Field boundaries with MULTIPOLYGON geometry | `fields` |
| 003 | `regions` | Regions and field membership | `regions`, `region_members` |
| 004 | `field_events` | Farm operations with 9 event types | `field_events`, `field_event_entries` |
| 005 | `photos_equipment_preferences_logos` | Photos, equipment, user preferences, group logos | `photos`, `event_photos`, `equipment`, `preferences`, `logos` |
| 006 | `plss_clu` | PLSS townships/sections, CLU reference data | `plss_townships`, `plss_sections`, `clu` |
| 007 | `plugins` | Plugin registry | `plugins` |
| 008 | `billing` | Credit accounts, ledger, price catalog | `credit_accounts`, `credit_ledger`, `price_catalog` |
| 009 | `email_config` | Per-group email delivery configuration | `email_configs` |
| 010 | `sampling` | Sampling plans with 5 algorithms | `sampling_plans` |
| 011 | `field_region_fk` | Add region_id FK + FSA/CLU columns to fields | (modifies `fields`) |
| 012 | `crop_years` | Crop year lifecycle + link to field events | `crop_years` (+ modifies `field_events`) |
| 013 | `field_boundary_versions` | Permanent geometry version history | `field_boundary_versions` |
| 014 | `point_datasets` | Point data collection + cleaning log | `point_datasets`, `point_cleaning_log` |
| 015 | `interpolation_prescriptions` | Interpolation surfaces + prescription zones | `interpolation_surfaces`, `prescriptions` |
| 016 | `adapt_mapping` | ADAPT entity ID mapping | `adapt_entity_map` |
| 017 | `sync` | Desktop sync state + conflict resolution | `sync_state`, `sync_conflicts` |
| 018 | `field_events_crop_year_id_required` | Backfill crop_year_id on field_events | (modifies `field_events`) |
| 019 | `core_datasets` | Plugin-attached dataset storage | `core_datasets` |
| 020 | `export_links` | Shareable download links with expiry | `export_links` |
| 021 | `api_keys` | Long-lived API bearer tokens | `api_keys` |
| 022 | `session_audit` | Login/logout audit trail | `session_audit` |
| 023 | `price_catalog_module_id` | Add module_id for plugin charge types | (modifies `price_catalog`) |
| 024 | `subscriptions` | Plugin subscription lifecycle | `subscriptions` |
| 025 | `field_events_crop_year_id_backfill` | Final crop_year_id NOT NULL constraint | (modifies `field_events`) |

## Dependency Chain

```
001 → 002 → 003 → 004 → 005 → 006 → 007 → 008 → 009 → 010
  → 011 → 012 → 013 → 014 → 015 → 016 → 017 → 018 → 019
  → 020 → 021 → 022 → 023 → 024 → 025
```

Linear chain — each migration depends on the previous one.

## Creating New Migrations

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "description_of_change"

# Create empty migration (for data migrations)
alembic revision -m "description_of_change"
```

### Conventions

- File naming: `{NNN}_{snake_case_description}.py` (e.g., `026_my_feature.py`)
- Revision IDs: Use the zero-padded number as revision (e.g., `"026"`)
- Down revision: Previous migration number (e.g., `"025"`)
- Always implement both `upgrade()` and `downgrade()`
- Data migrations should be idempotent
- Test both upgrade and downgrade paths

### Example Migration

```python
"""026 — Add weather_station table."""

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "weather_stations",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("weather_stations")
```

## Key Schema Details

### Geometry Columns

All spatial columns use SRID 4326 (WGS84):
- `fields.geometry` — MULTIPOLYGON
- `field_boundary_versions.geometry` — MULTIPOLYGON
- `sampling_plans.points` — MULTIPOINT
- `prescriptions.geometry` — MULTIPOLYGON
- `photos.location` — POINT
- `plss_townships.geom` — MULTIPOLYGON
- `plss_sections.geom` — MULTIPOLYGON
- `clu.geom` — MULTIPOLYGON

### JSONB Columns

Flexible structured data:
- `field_events.data` — Event-type-specific operation data
- `field_event_entries.data` — Entry-type-specific data
- `plugins.manifest` — Plugin manifest
- `core_datasets.metadata_` — Plugin dataset metadata
- `prescriptions.zones` — Zone definitions with rates
- `preferences.data` — User settings
- `groups.settings` — Group configuration
- `sync_conflicts.server_data / client_data` — Conflict payloads

### Soft Delete Tables

Tables with `deleted_at` column (NULL = active):
- `users`, `groups`, `fields`, `regions`, `crop_years`
- `field_events`, `photos`, `equipment`
- `point_datasets`, `prescriptions`, `core_datasets`

### Permanent History Tables (no soft delete)

- `token_blacklist` — Revoked JWTs
- `session_audit` — Login/logout events
- `field_boundary_versions` — Geometry history
- `credit_ledger` — Immutable transaction log
- `point_cleaning_log` — Data cleaning audit trail
