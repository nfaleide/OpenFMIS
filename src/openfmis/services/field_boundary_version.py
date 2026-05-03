"""FieldBoundaryVersion service — versioned geometry history."""

import json
from uuid import UUID

from geoalchemy2 import Geography
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import cast, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.field_boundary_version import FieldBoundaryVersion
from openfmis.schemas.field_boundary_version import BoundaryVersionCreate


class FieldBoundaryVersionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, version_id: UUID) -> FieldBoundaryVersion:
        result = await self.db.execute(
            select(FieldBoundaryVersion).where(FieldBoundaryVersion.id == version_id)
        )
        v = result.scalar_one_or_none()
        if v is None:
            raise NotFoundError("Boundary version not found")
        return v

    async def list_by_field(self, field_id: UUID) -> list[FieldBoundaryVersion]:
        result = await self.db.execute(
            select(FieldBoundaryVersion)
            .where(FieldBoundaryVersion.field_id == field_id)
            .order_by(FieldBoundaryVersion.version.desc())
        )
        return list(result.scalars().all())

    async def create(
        self, data: BoundaryVersionCreate, created_by: UUID | None = None
    ) -> FieldBoundaryVersion:
        # Get current max version for this field
        result = await self.db.execute(
            select(func.max(FieldBoundaryVersion.version)).where(
                FieldBoundaryVersion.field_id == data.field_id
            )
        )
        max_version = result.scalar_one_or_none() or 0

        # Mark all existing versions as non-current
        await self.db.execute(
            update(FieldBoundaryVersion)
            .where(FieldBoundaryVersion.field_id == data.field_id)
            .values(is_current=False)
        )

        geom_expr = func.ST_SetSRID(
            func.ST_GeomFromGeoJSON(json.dumps(data.geometry_geojson)),
            4326,
        )

        v = FieldBoundaryVersion(
            field_id=data.field_id,
            geometry=geom_expr,
            source=data.source,
            epsg=data.epsg,
            version=max_version + 1,
            is_current=True,
            created_by=created_by or data.created_by,
        )
        self.db.add(v)
        await self.db.flush()

        # Compute area
        area_result = await self.db.execute(
            select(
                func.ST_Area(cast(FieldBoundaryVersion.geometry, Geography)) / 4046.8564224
            ).where(FieldBoundaryVersion.id == v.id)
        )
        area = area_result.scalar_one_or_none()
        if area is not None:
            v.area_acres = round(float(area), 2)
            await self.db.flush()

        await self.db.refresh(v)
        return v

    async def get_geometry_geojson(self, version_id: UUID) -> dict | None:
        result = await self.db.execute(
            select(ST_AsGeoJSON(FieldBoundaryVersion.geometry)).where(
                FieldBoundaryVersion.id == version_id
            )
        )
        geojson_str = result.scalar_one_or_none()
        if geojson_str is None:
            return None
        return json.loads(geojson_str)
