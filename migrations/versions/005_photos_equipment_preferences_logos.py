"""Add photos, event_photos, equipment, preferences, logos tables.

Revision ID: 005
Revises: 004
Create Date: 2025-01-01 00:00:04.000000
"""

from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Photos ─────────────────────────────────────────────────
    op.create_table(
        "photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("comments", sa.Text, nullable=True),
        sa.Column("storage_url", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("object_type", sa.String(50), nullable=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("field_event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_events.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "event_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("photo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("field_events.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Equipment ──────────────────────────────────────────────
    op.create_table(
        "equipment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id"), nullable=False, index=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("make", sa.String(255), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("equipment_type", sa.String(100), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Preferences ────────────────────────────────────────────
    op.create_table(
        "preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "namespace", name="uq_user_preference"),
    )

    # ── Logos ──────────────────────────────────────────────────
    op.create_table(
        "logos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("storage_url", sa.String(1024), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("logos")
    op.drop_table("preferences")
    op.drop_table("equipment")
    op.drop_table("event_photos")
    op.drop_table("photos")
