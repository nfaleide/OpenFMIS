"""006 — PLSS townships/sections and CLU tables.

Revision ID: 006
Revises: 005
Create Date: 2026-03-09

Note: geoalchemy2 Geometry columns auto-create a GIST index on the geom
column during CREATE TABLE, so we only add the non-spatial indexes here.
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── PLSS Townships ────────────────────────────────────────────
    op.create_table(
        "plss_townships",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("gid", sa.Integer, nullable=True),
        sa.Column("lndkey", sa.String(50), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("primer", sa.Integer, nullable=True),
        sa.Column("town", sa.Integer, nullable=True),
        sa.Column("twnfrt", sa.String(10), nullable=True),
        sa.Column("twndir", sa.String(1), nullable=True),
        sa.Column("range_", sa.Integer, nullable=True),
        sa.Column("rngdir", sa.String(1), nullable=True),
        sa.Column("rngfrt", sa.String(10), nullable=True),
        sa.Column("twndup", sa.String(10), nullable=True),
        sa.Column("twntype", sa.String(10), nullable=True),
        sa.Column("datecreate", sa.Date, nullable=True),
        sa.Column("datemodifi", sa.Date, nullable=True),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("fips_c", sa.String(100), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
    )
    # Non-spatial indexes (spatial GIST already created by geoalchemy2)
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_twn_lndkey ON plss_townships (lndkey)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_twn_state ON plss_townships (state)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_twn_state_town_range ON plss_townships (state, town, twndir, range_, rngdir)"))

    # ── PLSS Sections ─────────────────────────────────────────────
    op.create_table(
        "plss_sections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("gid", sa.Integer, nullable=True),
        sa.Column("lndkey", sa.String(50), nullable=True),
        sa.Column("sectn", sa.Integer, nullable=True),
        sa.Column("secfrt", sa.String(10), nullable=True),
        sa.Column("secdup", sa.String(10), nullable=True),
        sa.Column("sectionkey", sa.String(50), nullable=True),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("mtrs", sa.String(50), nullable=True),
        sa.Column("mc_density", sa.Float, nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("fips_c", sa.String(100), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_sec_mtrs ON plss_sections (mtrs)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_sec_lndkey ON plss_sections (lndkey)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_plss_sec_fips ON plss_sections (fips_c)"))

    # ── CLU (Common Land Units) ───────────────────────────────────
    op.create_table(
        "clu",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("state", sa.String(2), nullable=False),
        sa.Column("county_fips", sa.String(5), nullable=True),
        sa.Column("calcacres", sa.Float, nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="MULTIPOLYGON", srid=4326),
            nullable=True,
        ),
    )
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clu_state_county ON clu (state, county_fips)"))


def downgrade() -> None:
    op.drop_table("clu")
    op.drop_table("plss_sections")
    op.drop_table("plss_townships")
