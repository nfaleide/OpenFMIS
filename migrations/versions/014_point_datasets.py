"""019 — Point datasets + cleaning log.

Revision ID: 019
Revises: 018
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "point_datasets",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("field_id", UUID(as_uuid=True),
                   sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("crop_year_id", UUID(as_uuid=True),
                   sa.ForeignKey("crop_years.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("value_column", sa.String(100), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("sample_date", sa.Date, nullable=True),
        sa.Column("source_file", sa.String(500), nullable=True),
        sa.Column("raw_layer", sa.String(255), nullable=True),
        sa.Column("clean_layer", sa.String(255), nullable=True),
        sa.Column("raw_count", sa.Integer, nullable=True),
        sa.Column("clean_count", sa.Integer, nullable=True),
        sa.Column("soil_lab", sa.String(255), nullable=True),
        sa.Column("soil_extractant", sa.String(100), nullable=True),
        sa.Column("primary_nutrient", sa.String(100), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_point_datasets_field", "point_datasets", ["field_id"])
    op.create_index("idx_point_datasets_crop_year", "point_datasets", ["crop_year_id"])
    op.create_index("idx_point_datasets_type", "point_datasets", ["dataset_type"])

    op.create_table(
        "point_cleaning_log",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("dataset_id", UUID(as_uuid=True),
                   sa.ForeignKey("point_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("points_removed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_cleaning_log_dataset", "point_cleaning_log", ["dataset_id"])


def downgrade() -> None:
    op.drop_index("idx_cleaning_log_dataset")
    op.drop_table("point_cleaning_log")
    op.drop_index("idx_point_datasets_type")
    op.drop_index("idx_point_datasets_crop_year")
    op.drop_index("idx_point_datasets_field")
    op.drop_table("point_datasets")
