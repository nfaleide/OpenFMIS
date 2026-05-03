"""Backfill crop_year_id on field_events and make NOT NULL.

For each field_event with crop_year_id IS NULL, finds or creates a
matching CropYear record (by label matching the int crop_year) in the
field's group, then sets crop_year_id.  After backfill, alters the column
to NOT NULL.

Revision ID: 032
Revises: 031
"""

import uuid
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find all field_events with NULL crop_year_id
    rows = conn.execute(
        sa.text("""
            SELECT fe.id, fe.crop_year, fe.field_id
            FROM field_events fe
            WHERE fe.crop_year_id IS NULL
        """)
    ).fetchall()

    for row in rows:
        event_id = row[0]
        crop_year_int = row[1]
        field_id = row[2]

        # Try to find an existing CropYear
        label = str(crop_year_int)
        existing = conn.execute(
            sa.text("""
                SELECT id FROM crop_years
                WHERE field_id = :field_id AND label = :label
                AND deleted_at IS NULL
                LIMIT 1
            """),
            {"field_id": field_id, "label": label},
        ).fetchone()

        if existing is not None:
            cy_id = existing[0]
        else:
            # Create a CropYear
            cy_id = uuid.uuid4()
            now = datetime.now(UTC)
            conn.execute(
                sa.text("""
                    INSERT INTO crop_years
                    (id, field_id, label, start_date, end_date, created_at, updated_at)
                    VALUES (:id, :field_id, :label, :start_date, :end_date, :now, :now)
                """),
                {
                    "id": cy_id,
                    "field_id": field_id,
                    "label": label,
                    "start_date": date(crop_year_int, 1, 1),
                    "end_date": date(crop_year_int, 12, 31),
                    "now": now,
                },
            )

        # Set crop_year_id
        conn.execute(
            sa.text("UPDATE field_events SET crop_year_id = :cy_id WHERE id = :event_id"),
            {"cy_id": cy_id, "event_id": event_id},
        )

    # Make NOT NULL
    op.alter_column(
        "field_events",
        "crop_year_id",
        existing_type=postgresql.UUID(),
        nullable=False,
    )


def downgrade() -> None:
    # Revert to nullable
    op.alter_column(
        "field_events",
        "crop_year_id",
        existing_type=postgresql.UUID(),
        nullable=True,
    )
