"""024 — Create core_datasets table for plugin dataset attachment.

Revision ID: 024
Revises: 023
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "core_datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("plugin_slug", sa.String(100), nullable=False),
        sa.Column("dataset_type", sa.String(100), nullable=False),
        sa.Column(
            "field_id",
            UUID(as_uuid=True),
            sa.ForeignKey("fields.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("storage_url", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_core_datasets_plugin_type",
        "core_datasets",
        ["plugin_slug", "dataset_type"],
    )
    op.create_index(
        "idx_core_datasets_field",
        "core_datasets",
        ["field_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_core_datasets_field", table_name="core_datasets")
    op.drop_index("idx_core_datasets_plugin_type", table_name="core_datasets")
    op.drop_table("core_datasets")
