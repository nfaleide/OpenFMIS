"""027 -- Create session_audit table for login/logout tracking.

Revision ID: 027
Revises: 026
Create Date: 2026-05-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_audit",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("jti", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_session_audit_user", "session_audit", ["user_id"])
    op.create_index(
        "idx_session_audit_user_created", "session_audit", ["user_id", "created_at"]
    )
    op.create_index("idx_session_audit_event_type", "session_audit", ["event_type"])


def downgrade() -> None:
    op.drop_index("idx_session_audit_event_type", table_name="session_audit")
    op.drop_index("idx_session_audit_user_created", table_name="session_audit")
    op.drop_index("idx_session_audit_user", table_name="session_audit")
    op.drop_table("session_audit")
