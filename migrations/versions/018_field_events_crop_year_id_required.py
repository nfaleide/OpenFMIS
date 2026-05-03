"""023 — Backfill crop_year_id on field_events; make NOT NULL.

For each field_event row with crop_year_id IS NULL, find or create
a CropYear matching (field_id, crop_year int). Then alter the column
to NOT NULL.

Revision ID: 023
Revises: 022
Create Date: 2026-05-02
"""

import uuid
from datetime import date

import sqlalchemy as sa
from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find all distinct (field_id, crop_year) combos with NULL crop_year_id
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT field_id, crop_year "
            "FROM field_events "
            "WHERE crop_year_id IS NULL AND deleted_at IS NULL"
        )
    ).fetchall()

    for field_id, crop_year in rows:
        # Check if a matching CropYear already exists
        existing = conn.execute(
            sa.text(
                "SELECT id FROM crop_years "
                "WHERE field_id = :fid AND label = :label AND deleted_at IS NULL "
                "LIMIT 1"
            ),
            {"fid": field_id, "label": str(crop_year)},
        ).fetchone()

        if existing:
            cy_id = existing[0]
        else:
            cy_id = uuid.uuid4()
            start = date(crop_year, 1, 1)
            end = date(crop_year, 12, 31)
            conn.execute(
                sa.text(
                    "INSERT INTO crop_years (id, field_id, label, start_date, end_date) "
                    "VALUES (:id, :fid, :label, :start, :end)"
                ),
                {
                    "id": cy_id,
                    "fid": field_id,
                    "label": str(crop_year),
                    "start": start,
                    "end": end,
                },
            )

        # Backfill all matching field_events
        conn.execute(
            sa.text(
                "UPDATE field_events "
                "SET crop_year_id = :cyid "
                "WHERE field_id = :fid AND crop_year = :cy AND crop_year_id IS NULL"
            ),
            {"cyid": cy_id, "fid": field_id, "cy": crop_year},
        )

    # Verify no NULLs remain
    null_count = conn.execute(
        sa.text(
            "SELECT count(*) FROM field_events WHERE crop_year_id IS NULL AND deleted_at IS NULL"
        )
    ).scalar()
    assert null_count == 0, f"Backfill incomplete: {null_count} rows still have NULL crop_year_id"

    # Make NOT NULL
    op.alter_column("field_events", "crop_year_id", nullable=False)


def downgrade() -> None:
    op.alter_column("field_events", "crop_year_id", nullable=True)
