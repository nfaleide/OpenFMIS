"""Add module_id to price_catalog for plugin charge type registry.

Revision ID: 028
Revises: 027
"""

from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_catalog", sa.Column("module_id", sa.String(100), nullable=True))
    op.create_index("idx_price_catalog_module_id", "price_catalog", ["module_id"])


def downgrade() -> None:
    op.drop_index("idx_price_catalog_module_id", table_name="price_catalog")
    op.drop_column("price_catalog", "module_id")
