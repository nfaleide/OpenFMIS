"""016 — Add region_id FK to fields, FSA/CLU columns.

Revision ID: 016
Revises: 015
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add region_id as nullable first
    op.add_column(
        "fields",
        sa.Column(
            "region_id", UUID(as_uuid=True),
            sa.ForeignKey("regions.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("idx_fields_region", "fields", ["region_id"])

    # FSA / CLU columns
    op.add_column("fields", sa.Column("fsa_tract", sa.String(50), nullable=True))
    op.add_column("fields", sa.Column("fsa_field", sa.String(50), nullable=True))
    op.add_column("fields", sa.Column("clu_id", sa.String(100), nullable=True))
    op.create_index("idx_fields_fsa_tract", "fields", ["fsa_tract"])
    op.create_index("idx_fields_clu_id", "fields", ["clu_id"])

    # Backfill: create a default region for each group that has fields
    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO regions (id, name, group_id, created_at, updated_at)
        SELECT gen_random_uuid(), 'Default Farm', f.group_id,
               now(), now()
        FROM (SELECT DISTINCT group_id FROM fields WHERE group_id IS NOT NULL) f
        WHERE NOT EXISTS (
            SELECT 1 FROM regions r WHERE r.group_id = f.group_id
        )
    """))
    # Set region_id for all fields that don't have one
    conn.execute(sa.text("""
        UPDATE fields SET region_id = (
            SELECT r.id FROM regions r WHERE r.group_id = fields.group_id LIMIT 1
        )
        WHERE region_id IS NULL
    """))

    # Make region_id non-nullable
    op.alter_column("fields", "region_id", nullable=False)


def downgrade() -> None:
    op.drop_index("idx_fields_clu_id")
    op.drop_index("idx_fields_fsa_tract")
    op.drop_column("fields", "clu_id")
    op.drop_column("fields", "fsa_field")
    op.drop_column("fields", "fsa_tract")
    op.drop_index("idx_fields_region")
    op.drop_column("fields", "region_id")
