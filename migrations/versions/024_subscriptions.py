"""Add subscriptions table for generic subscription lifecycle.

Revision ID: 031
Revises: 030
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(10), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plugin_id", sa.String(100), nullable=False),
        sa.Column("subscription_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'cancelled', 'suspended')",
            name="ck_subscription_status",
        ),
        sa.CheckConstraint(
            "owner_type IN ('user', 'group')",
            name="ck_subscription_owner_type",
        ),
    )
    op.create_index("idx_subscriptions_owner", "subscriptions", ["owner_type", "owner_id"])
    op.create_index("idx_subscriptions_plugin", "subscriptions", ["plugin_id"])
    op.create_index("idx_subscriptions_status", "subscriptions", ["status"])
    op.create_index("idx_subscriptions_expires", "subscriptions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_subscriptions_expires", table_name="subscriptions")
    op.drop_index("idx_subscriptions_status", table_name="subscriptions")
    op.drop_index("idx_subscriptions_plugin", table_name="subscriptions")
    op.drop_index("idx_subscriptions_owner", table_name="subscriptions")
    op.drop_table("subscriptions")
