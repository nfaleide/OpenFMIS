"""Add field_events and field_event_entries tables.

Revision ID: 004
Revises: 003
Create Date: 2025-01-01 00:00:03.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type explicitly, then use create_type=False on the column
    # so that create_table doesn't try to create it again.
    event_type_enum = postgresql.ENUM(
        "crop_protection",
        "fertilizing",
        "harvest",
        "irrigation",
        "insurance",
        "planting",
        "scouting",
        "soil_testing",
        "tillage",
        name="event_type_enum",
        create_type=False,
    )
    event_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "field_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "field_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fields.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "event_type",
            event_type_enum,
            nullable=False,
            index=True,
        ),
        sa.Column("crop_year", sa.Integer, nullable=False, index=True),
        sa.Column("operation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("field_events.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("version", sa.Integer, default=1, nullable=False),
        sa.Column("is_current", sa.Boolean, default=True, nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "field_event_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("field_events.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("entry_type", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer, default=0, nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("field_event_entries")
    op.drop_table("field_events")
    op.execute("DROP TYPE IF EXISTS event_type_enum")
