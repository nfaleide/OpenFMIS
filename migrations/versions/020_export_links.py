"""025 — Create export_links table for shareable download links.

Revision ID: 025
Revises: 024
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("filters", JSONB, nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("download_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_downloads", sa.Integer, nullable=True),
        sa.Column("filename", sa.Text, nullable=False, server_default="'export'"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_export_links_hash", "export_links", ["hash"])
    op.create_index("idx_export_links_expires", "export_links", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_export_links_expires", table_name="export_links")
    op.drop_index("idx_export_links_hash", table_name="export_links")
    op.drop_table("export_links")
