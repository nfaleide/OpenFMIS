"""020 — Interpolation surfaces + prescriptions.

Revision ID: 020
Revises: 019
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interpolation_surfaces",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("dataset_id", UUID(as_uuid=True),
                   sa.ForeignKey("point_datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_id", UUID(as_uuid=True),
                   sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("cell_size_m", sa.Float, nullable=False),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("layer_ref", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_interp_surfaces_dataset", "interpolation_surfaces", ["dataset_id"])
    op.create_index("idx_interp_surfaces_field", "interpolation_surfaces", ["field_id"])

    op.create_table(
        "prescriptions",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("field_id", UUID(as_uuid=True),
                   sa.ForeignKey("fields.id", ondelete="CASCADE"), nullable=False),
        sa.Column("crop_year_id", UUID(as_uuid=True),
                   sa.ForeignKey("crop_years.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("product", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("zone_count", sa.Integer, nullable=True),
        sa.Column("classification", sa.String(50), nullable=True),
        sa.Column("zones", JSONB, nullable=True),
        sa.Column("geometry", Geometry("MULTIPOLYGON", srid=4326), nullable=True),
        sa.Column("source_surface_id", UUID(as_uuid=True),
                   sa.ForeignKey("interpolation_surfaces.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rec_model", sa.String(255), nullable=True),
        sa.Column("export_formats", JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                   server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_prescriptions_field", "prescriptions", ["field_id"])
    op.create_index("idx_prescriptions_crop_year", "prescriptions", ["crop_year_id"])


def downgrade() -> None:
    op.drop_index("idx_prescriptions_crop_year")
    op.drop_index("idx_prescriptions_field")
    op.drop_table("prescriptions")
    op.drop_index("idx_interp_surfaces_field")
    op.drop_index("idx_interp_surfaces_dataset")
    op.drop_table("interpolation_surfaces")
