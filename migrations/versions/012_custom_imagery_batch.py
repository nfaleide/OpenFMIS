"""012 — Custom imagery uploads, batch analysis, email config.

Revision ID: 012
Revises: 011
Create Date: 2026-03-10
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Custom scenes (user uploads) ───────────────────────────────────────
    op.create_table(
        "custom_scenes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("crs", sa.String(50), nullable=True),
        sa.Column("band_count", sa.Integer, nullable=True),
        sa.Column("band_names", JSONB, nullable=True),
        sa.Column("band_metadata", JSONB, nullable=True),
        sa.Column("bounds", JSONB, nullable=True),
        sa.Column(
            "footprint",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pixel_resolution_m", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("scene_record_id", UUID(as_uuid=True), sa.ForeignKey("scene_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_custom_scenes_group ON custom_scenes (group_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_custom_scenes_status ON custom_scenes (status)"))

    # ── Batch analyses ─────────────────────────────────────────────────────
    op.create_table(
        "batch_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("field_ids", JSONB, nullable=False),
        sa.Column("scene_id", sa.String(200), nullable=False),
        sa.Column("index_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("job_ids", JSONB, nullable=True),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Email configs ──────────────────────────────────────────────────────
    op.create_table(
        "email_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("delivery_method", sa.String(20), nullable=False, server_default="smtp"),
        sa.Column("smtp_host", sa.String(255), nullable=True),
        sa.Column("smtp_port", sa.Integer, nullable=True),
        sa.Column("smtp_username", sa.String(255), nullable=True),
        sa.Column("smtp_password_encrypted", sa.Text, nullable=True),
        sa.Column("smtp_use_tls", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("smtp_from_address", sa.String(255), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("webhook_headers", JSONB, nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── Add preview columns to scene_notifications ─────────────────────────
    op.add_column("scene_notifications", sa.Column("preview_urls", JSONB, nullable=True))
    op.add_column("scene_notifications", sa.Column("thumbnail_status", sa.String(20), server_default="pending"))


def downgrade() -> None:
    op.drop_column("scene_notifications", "thumbnail_status")
    op.drop_column("scene_notifications", "preview_urls")
    op.drop_table("email_configs")
    op.drop_table("batch_analyses")
    op.drop_table("custom_scenes")
