"""017 — Crop years + field_events.crop_year_id FK.

Revision ID: 017
Revises: 016
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crop_years",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("field_id", UUID(as_uuid=True),
                   sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("crop_code", sa.Integer, nullable=True),
        sa.Column("tillage", sa.String(50), nullable=True),
        sa.Column("planting_date", sa.Date, nullable=True),
        sa.Column("harvest_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_crop_years_field", "crop_years", ["field_id"])

    # Add crop_year_id FK to field_events
    op.add_column(
        "field_events",
        sa.Column(
            "crop_year_id", UUID(as_uuid=True),
            sa.ForeignKey("crop_years.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_field_events_crop_year", "field_events", ["crop_year_id"])


def downgrade() -> None:
    op.drop_index("idx_field_events_crop_year")
    op.drop_column("field_events", "crop_year_id")
    op.drop_index("idx_crop_years_field")
    op.drop_table("crop_years")
