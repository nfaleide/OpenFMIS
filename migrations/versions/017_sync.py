"""022 — Sync state + conflicts tables.

Revision ID: 022
Revises: 021
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_state",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", UUID(as_uuid=True),
                   sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", UUID(as_uuid=True),
                   sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pending_conflicts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "group_id", "client_id",
                            name="uq_sync_state_user_group_client"),
    )
    op.create_index("idx_sync_state_user", "sync_state", ["user_id"])
    op.create_index("idx_sync_state_group", "sync_state", ["group_id"])

    op.create_table(
        "sync_conflicts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sync_state_id", UUID(as_uuid=True),
                   sa.ForeignKey("sync_state.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("server_data", JSONB, nullable=True),
        sa.Column("client_data", JSONB, nullable=True),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolved_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_sync_conflicts_state", "sync_conflicts", ["sync_state_id"])


def downgrade() -> None:
    op.drop_index("idx_sync_conflicts_state")
    op.drop_table("sync_conflicts")
    op.drop_index("idx_sync_state_group")
    op.drop_index("idx_sync_state_user")
    op.drop_table("sync_state")
