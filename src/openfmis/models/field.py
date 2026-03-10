"""Field model — agricultural field boundaries with versioned geometry.

Replaces legacy 'fields' table. Key changes from legacy:
- MULTIPOLYGON (was POLYGON) for complex field shapes
- SRID 4326 (was 4269) for global compatibility
- UUID PK (was SERIAL)
- supersedes_id for version chains (was integer version column)
- Soft delete via deleted_at
"""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from openfmis.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Field(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "fields"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Geometry — MULTIPOLYGON, SRID 4326 (WGS84)
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=True,
    )

    # Area in acres (computed from geometry, cached)
    area_acres: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Ownership — which group owns this field
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )

    # Created by which user
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # Version chain — points to the field this version supersedes
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fields.id"),
        nullable=True,
        index=True,
    )

    # Version number within the chain (1 = original)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Whether this is the latest version in its chain
    is_current: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Extensible metadata (crop type, soil info, custom attributes, etc.)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True, default=dict)

    # Relationships
    group = relationship("Group", lazy="selectin")
    creator = relationship("User", lazy="selectin")
    supersedes = relationship("Field", remote_side="Field.id", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Field {self.name} v{self.version}>"
