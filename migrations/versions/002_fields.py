"""Add fields table with MULTIPOLYGON geometry and version chain.

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 00:00:01.000000
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column("area_acres", sa.Float, nullable=True),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("groups.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fields.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("version", sa.Integer, default=1, nullable=False),
        sa.Column("is_current", sa.Boolean, default=True, nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
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

    # Note: GeoAlchemy2 automatically creates a spatial index (idx_fields_geometry)
    # when the Geometry column is created via create_table, so no explicit create_index needed.


def downgrade() -> None:
    op.drop_index("idx_fields_geometry", table_name="fields")
    op.drop_table("fields")
