"""009 — Email delivery configuration per group.

Revision ID: 009
Revises: 008
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_table("email_configs")
