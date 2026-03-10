"""011 — Configurable band math: spectral index definitions, relax analysis_jobs constraint.

Revision ID: 011
Revises: 010
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Spectral index definitions ─────────────────────────────────────────
    op.create_table(
        "spectral_index_definitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("formula", sa.Text, nullable=False),
        sa.Column("required_bands", JSONB, nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="custom"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("value_range", JSONB, nullable=True),
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_id", UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # ── Relax analysis_jobs.index_type constraint ──────────────────────────
    conn.execute(text("ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS ck_analysis_job_index_type"))
    conn.execute(text("ALTER TABLE analysis_jobs ALTER COLUMN index_type TYPE VARCHAR(50)"))

    # ── Seed builtin indices ───────────────────────────────────────────────
    builtins = [
        ("ndvi", "NDVI", "(nir - red) / (nir + red)", '["nir","red"]', "vegetation"),
        ("gndvi", "GNDVI", "(nir - green) / (nir + green)", '["green","nir"]', "vegetation"),
        ("evi", "EVI", "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)", '["blue","nir","red"]', "vegetation"),
        ("savi", "SAVI", "(nir - red) * (1 + L) / (nir + red + L)", '["nir","red"]', "vegetation"),
        ("osavi", "OSAVI", "(nir - red) / (nir + red + 0.16)", '["nir","red"]', "vegetation"),
        ("msavi2", "MSAVI2", "(2 * nir + 1 - sqrt((2 * nir + 1) ** 2 - 8 * (nir - red))) / 2", '["nir","red"]', "vegetation"),
        ("ndre", "NDRE", "(nir - rededge1) / (nir + rededge1)", '["nir","rededge1"]', "vegetation"),
        ("vari", "VARI", "(green - red) / (green + red - blue)", '["blue","green","red"]', "vegetation"),
        ("cigreen", "CI Green", "(nir / green) - 1", '["green","nir"]', "vegetation"),
        ("cirededge", "CI Red-Edge", "(nir / rededge1) - 1", '["nir","rededge1"]', "vegetation"),
        ("wdrvi", "WDRVI", "(0.1 * nir - red) / (0.1 * nir + red)", '["nir","red"]', "vegetation"),
        ("arvi", "ARVI", "(nir - (2 * red - blue)) / (nir + (2 * red - blue))", '["blue","nir","red"]', "vegetation"),
        ("nir", "NIR", "nir", '["nir"]', "band"),
        ("ndwi", "NDWI", "(green - nir) / (green + nir)", '["green","nir"]', "water"),
        ("ndmi", "NDMI", "(nir - swir16) / (nir + swir16)", '["nir","swir16"]', "water"),
        ("nbr", "NBR", "(nir - swir22) / (nir + swir22)", '["nir","swir22"]', "fire"),
        ("bsi", "BSI", "((swir16 + red) - (nir + blue)) / ((swir16 + red) + (nir + blue))", '["blue","nir","red","swir16"]', "soil"),
        ("vv", "VV Polarization", "vv", '["vv"]', "sar"),
        ("vh", "VH Polarization", "vh", '["vh"]', "sar"),
        ("vv_vh_ratio", "VV/VH Ratio", "vv / vh", '["vh","vv"]', "sar"),
        ("rvi_sar", "RVI (SAR)", "(4 * vh) / (vv + vh)", '["vh","vv"]', "sar"),
    ]

    for slug, name, formula, bands, category in builtins:
        conn.execute(text(
            "INSERT INTO spectral_index_definitions (slug, display_name, formula, required_bands, category, is_builtin) "
            "VALUES (:slug, :name, :formula, CAST(:bands AS jsonb), :category, true) "
            "ON CONFLICT (slug) DO NOTHING"
        ), {"slug": slug, "name": name, "formula": formula, "bands": bands, "category": category})


def downgrade() -> None:
    op.drop_table("spectral_index_definitions")
    # Re-add constraint (lossy — only valid if data is clean)
    op.get_bind().execute(sa.text(
        "ALTER TABLE analysis_jobs ADD CONSTRAINT ck_analysis_job_index_type "
        "CHECK (index_type IN ('ndvi', 'ndwi', 'evi', 'ndre', 'savi'))"
    ))
    op.get_bind().execute(sa.text(
        "ALTER TABLE analysis_jobs ALTER COLUMN index_type TYPE VARCHAR(20)"
    ))
