"""018 — Field boundary versions (permanent geometry history).

Revision ID: 018
Revises: 017
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import UUID

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_boundary_versions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("field_id", UUID(as_uuid=True),
                   sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geometry", Geometry("MULTIPOLYGON", srid=4326), nullable=False),
        sa.Column("area_acres", sa.Float, nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("epsg", sa.Integer, nullable=False, server_default="4326"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=True),
                   sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_boundary_versions_field", "field_boundary_versions", ["field_id"])


def downgrade() -> None:
    op.drop_index("idx_boundary_versions_field")
    op.drop_table("field_boundary_versions")
