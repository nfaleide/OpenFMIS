"""021 — ADAPT entity mapping table.

Revision ID: 021
Revises: 020
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adapt_entity_map",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("internal_type", sa.String(50), nullable=False),
        sa.Column("internal_id", UUID(as_uuid=True), nullable=False),
        sa.Column("adapt_type", sa.String(50), nullable=False),
        sa.Column("adapt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("adapt_role", sa.String(50), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_adapt_internal_type", "adapt_entity_map", ["internal_type"])
    op.create_index("idx_adapt_internal_id", "adapt_entity_map", ["internal_id"])
    op.create_index(
        "ix_adapt_entity_map_internal", "adapt_entity_map",
        ["internal_type", "internal_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_adapt_entity_map_internal")
    op.drop_index("idx_adapt_internal_id")
    op.drop_index("idx_adapt_internal_type")
    op.drop_table("adapt_entity_map")
