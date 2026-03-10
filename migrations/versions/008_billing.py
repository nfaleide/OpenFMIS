"""008 — Credit accounts, ledger, and price catalog.

Revision ID: 008
Revises: 007
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Credit accounts (one per user or group) ───────────────────────────
    op.create_table(
        "credit_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("owner_type", sa.String(10), nullable=False),   # "user" | "group"
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("balance", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("owner_type", "owner_id", name="uq_credit_account_owner"),
        sa.CheckConstraint("owner_type IN ('user', 'group')", name="ck_credit_account_owner_type"),
        sa.CheckConstraint("balance >= 0", name="ck_credit_account_balance_nonneg"),
    )
    op.create_index("idx_credit_accounts_owner", "credit_accounts", ["owner_type", "owner_id"])

    # ── Immutable credit ledger ────────────────────────────────────────────
    op.create_table(
        "credit_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_type", sa.String(20), nullable=False),   # "purchase" | "consume" | "refund" | "adjustment"
        sa.Column("amount", sa.Integer, nullable=False),           # positive = credit in, negative = credit out
        sa.Column("balance_after", sa.Integer, nullable=False),    # snapshot of balance after this entry
        sa.Column("reference", sa.String(255), nullable=True),     # e.g. "scene:uuid", "invoice:123"
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('purchase', 'consume', 'refund', 'adjustment')",
            name="ck_ledger_entry_type",
        ),
    )
    op.create_index("idx_credit_ledger_account", "credit_ledger", ["account_id"])
    op.create_index("idx_credit_ledger_account_created", "credit_ledger", ["account_id", "created_at"])

    # ── Price catalog ──────────────────────────────────────────────────────
    op.create_table(
        "price_catalog",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("operation", sa.String(100), nullable=False, unique=True),
        sa.Column("credit_cost", sa.Integer, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("credit_cost >= 0", name="ck_price_catalog_cost_nonneg"),
    )
    op.create_index("idx_price_catalog_operation", "price_catalog", ["operation"], unique=True)
    op.create_index("idx_price_catalog_active", "price_catalog", ["is_active"])

    # Seed default prices
    op.execute(
        sa.text("""
        INSERT INTO price_catalog (operation, credit_cost, description) VALUES
            ('scene_analysis',    10, 'Satellite scene analysis per field'),
            ('field_export',       1, 'Export field boundary (shapefile/GeoJSON/KML)'),
            ('bulk_import',        2, 'Import vector file with field boundaries'),
            ('clu_lookup',         0, 'CLU spatial query (free)'),
            ('plss_lookup',        0, 'PLSS spatial query (free)')
        """)
    )


def downgrade() -> None:
    op.drop_table("price_catalog")
    op.drop_table("credit_ledger")
    op.drop_table("credit_accounts")
