"""015 — Sampling plans: field sample point generation and collection tracking.

Revision ID: 015
Revises: 014
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sampling_algorithm_enum = sa.Enum(
        "random", "grid", "clustered", "w", "ssus", name="sampling_algorithm_enum"
    )
    sampling_plan_status_enum = sa.Enum(
        "draft", "active", "in_progress", "completed", "archived",
        name="sampling_plan_status_enum",
    )

    op.create_table(
        "sampling_plans",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "field_id", UUID(as_uuid=True),
            sa.ForeignKey("fields.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "zone_id", UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("algorithm", sampling_algorithm_enum, nullable=False),
        sa.Column(
            "status", sampling_plan_status_enum,
            nullable=False, server_default="draft",
        ),
        sa.Column("point_count", sa.Integer, nullable=False),
        sa.Column("min_distance", sa.Float, nullable=False, server_default="0"),
        sa.Column("buffer_distance", sa.Float, nullable=False, server_default="0"),
        sa.Column("cluster_count", sa.Integer, nullable=True),
        sa.Column("min_cluster_distance", sa.Float, nullable=True),
        sa.Column("points", Geometry("MULTIPOINT", srid=4326), nullable=True),
        sa.Column("points_geojson", JSONB, nullable=True),
        sa.Column(
            "points_completed", sa.Integer,
            nullable=False, server_default="0",
        ),
        sa.Column("collection_notes", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.CheckConstraint(
            "point_count >= 1 AND point_count <= 999",
            name="ck_sampling_point_count",
        ),
        sa.CheckConstraint("min_distance >= 0", name="ck_sampling_min_distance"),
        sa.CheckConstraint("buffer_distance >= 0", name="ck_sampling_buffer_distance"),
        sa.CheckConstraint("points_completed >= 0", name="ck_sampling_points_completed"),
    )

    op.create_index("idx_sampling_plans_field", "sampling_plans", ["field_id"])
    op.create_index("idx_sampling_plans_zone", "sampling_plans", ["zone_id"])
    op.create_index("idx_sampling_plans_created_by", "sampling_plans", ["created_by"])
    op.create_index("idx_sampling_plans_status", "sampling_plans", ["status"])
    op.create_index("idx_sampling_plans_field_status", "sampling_plans", ["field_id", "status"])


def downgrade() -> None:
    op.drop_table("sampling_plans")
    op.execute("DROP TYPE IF EXISTS sampling_algorithm_enum")
    op.execute("DROP TYPE IF EXISTS sampling_plan_status_enum")
