"""010 — Phase 3b/3c/3d: saved classifications, scene notifications, notification preferences.

Revision ID: 010
Revises: 009
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Saved classification presets ───────────────────────────────────────
    op.create_table(
        "saved_classifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("index_type", sa.String(20), nullable=False),
        sa.Column("num_classes", sa.Integer, nullable=False, server_default="5"),
        sa.Column("breakpoints", JSONB, nullable=False),
        sa.Column("colors", JSONB, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_saved_class_user ON saved_classifications (user_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_saved_class_index ON saved_classifications (index_type)"))

    # ── Scene notifications ────────────────────────────────────────────────
    op.create_table(
        "scene_notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.String(200), nullable=False),
        sa.Column("field_id", UUID(as_uuid=True), sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", sa.String(50), nullable=False, server_default="new_scene"),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("viewed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("visible", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_notif_user ON scene_notifications (user_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_notif_scene ON scene_notifications (scene_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_notif_viewed ON scene_notifications (user_id, viewed) WHERE visible = true"))

    # ── Notification preferences ───────────────────────────────────────────
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("email_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("scene_types", JSONB, nullable=True),
        sa.Column("settings", JSONB, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notification_preferences")
    op.drop_table("scene_notifications")
    op.drop_table("saved_classifications")
