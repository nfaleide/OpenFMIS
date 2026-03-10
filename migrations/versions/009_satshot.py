"""009 — Satshot imagery: scene cache, analysis zones, analysis jobs.

Revision ID: 009
Revises: 008
Create Date: 2026-03-10
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Sentinel-2 scene cache ─────────────────────────────────────────────
    op.create_table(
        "scene_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("scene_id", sa.String(200), nullable=False, unique=True),
        sa.Column("collection", sa.String(100), nullable=False, server_default="sentinel-2-l2a"),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_cover", sa.Float, nullable=True),
        sa.Column("bbox", JSONB, nullable=True),          # [min_lon, min_lat, max_lon, max_lat]
        sa.Column("assets", JSONB, nullable=False, server_default=sa.text("'{}'")),   # band href map
        sa.Column("stac_properties", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "footprint",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column(
            "cached_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scene_scene_id ON scene_records (scene_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scene_acquired ON scene_records (acquired_at DESC)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_scene_cloud ON scene_records (cloud_cover)"))

    # ── Analysis zones (sub-field polygons) ───────────────────────────────
    op.create_table(
        "analysis_zones",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("field_id", UUID(as_uuid=True), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "geometry",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_zones_field ON analysis_zones (field_id)"))

    # ── Analysis jobs ──────────────────────────────────────────────────────
    op.create_table(
        "analysis_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("field_id", UUID(as_uuid=True), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", UUID(as_uuid=True), sa.ForeignKey("analysis_zones.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scene_id", sa.String(200), nullable=False),   # references scene_records.scene_id
        sa.Column("index_type", sa.String(20), nullable=False),  # "ndvi" | "ndwi" | "evi" | "ndre"
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("result", JSONB, nullable=True),               # {mean, min, max, std, p10, p90, pixel_count}
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("credits_consumed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "index_type IN ('ndvi', 'ndwi', 'evi', 'ndre', 'savi')",
            name="ck_analysis_job_index_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'complete', 'failed')",
            name="ck_analysis_job_status",
        ),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_jobs_field ON analysis_jobs (field_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs (status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_analysis_jobs_scene ON analysis_jobs (scene_id)"))


def downgrade() -> None:
    op.drop_table("analysis_jobs")
    op.drop_table("analysis_zones")
    op.drop_table("scene_records")
