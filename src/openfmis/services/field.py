"""FieldService — CRUD with MULTIPOLYGON geometry and supersedes_id versioning."""

import json
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.field import Field
from openfmis.schemas.field import FieldCreate, FieldUpdate


class FieldService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, field_id: UUID, include_deleted: bool = False) -> Field:
        query = select(Field).where(Field.id == field_id)
        if not include_deleted:
            query = query.where(Field.deleted_at.is_(None))
        result = await self.db.execute(query)
        field = result.scalar_one_or_none()
        if field is None:
            raise NotFoundError("Field not found")
        return field

    async def list_fields(
        self,
        offset: int = 0,
        limit: int = 50,
        group_id: UUID | None = None,
        current_only: bool = True,
    ) -> tuple[list[Field], int]:
        query = select(Field).where(Field.deleted_at.is_(None))
        count_query = select(func.count()).select_from(Field).where(Field.deleted_at.is_(None))

        if current_only:
            query = query.where(Field.is_current.is_(True))
            count_query = count_query.where(Field.is_current.is_(True))

        if group_id is not None:
            query = query.where(Field.group_id == group_id)
            count_query = count_query.where(Field.group_id == group_id)

        query = query.order_by(Field.name).offset(offset).limit(limit)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        result = await self.db.execute(query)
        fields = list(result.scalars().all())
        return fields, total

    async def create_field(self, data: FieldCreate, created_by: UUID | None = None) -> Field:
        field = Field(
            name=data.name,
            description=data.description,
            group_id=data.group_id,
            created_by=created_by,
            version=1,
            is_current=True,
            metadata_=data.metadata_,
        )

        if data.geometry_geojson is not None:
            field.geometry = self._geojson_to_wkb_element(data.geometry_geojson)

        self.db.add(field)
        await self.db.flush()

        # Compute area if geometry was provided
        if data.geometry_geojson is not None:
            await self._update_area(field)

        await self.db.refresh(field)
        return field

    async def update_field(self, field_id: UUID, data: FieldUpdate) -> Field:
        field = await self.get_by_id(field_id)

        update_data = data.model_dump(exclude_unset=True)
        for attr, value in update_data.items():
            setattr(field, attr, value)

        await self.db.flush()
        await self.db.refresh(field)
        return field

    async def update_geometry(self, field_id: UUID, geometry_geojson: dict) -> Field:
        """Create a new version of the field with updated geometry.

        The old version is marked is_current=False.
        """
        old_field = await self.get_by_id(field_id)

        # Find the root of the version chain
        await self._find_chain_root(old_field)

        # Mark old as non-current
        old_field.is_current = False
        await self.db.flush()

        # Create new version
        new_field = Field(
            name=old_field.name,
            description=old_field.description,
            group_id=old_field.group_id,
            created_by=old_field.created_by,
            supersedes_id=old_field.id,
            version=old_field.version + 1,
            is_current=True,
            metadata_=old_field.metadata_,
            geometry=self._geojson_to_wkb_element(geometry_geojson),
        )
        self.db.add(new_field)
        await self.db.flush()

        await self._update_area(new_field)
        await self.db.refresh(new_field)
        return new_field

    async def get_version_history(self, field_id: UUID) -> list[Field]:
        """Get all versions in the chain, newest first."""
        # Walk backwards to root, then collect all forward
        current = await self.get_by_id(field_id, include_deleted=True)
        root = await self._find_chain_root_field(current)

        # Collect all versions from root forward
        versions = [root]
        seen = {root.id}

        # Find all fields that supersede something in our chain
        while True:
            result = await self.db.execute(
                select(Field).where(
                    Field.supersedes_id.in_(
                        [v.id for v in versions if v.id not in seen or v.id == versions[-1].id]
                    ),
                    Field.id.notin_(seen),
                )
            )
            next_versions = list(result.scalars().all())
            if not next_versions:
                break
            for v in next_versions:
                seen.add(v.id)
                versions.append(v)

        # Sort newest first
        versions.sort(key=lambda f: f.version, reverse=True)
        return versions

    async def soft_delete(self, field_id: UUID) -> None:
        from datetime import UTC, datetime

        field = await self.get_by_id(field_id)
        field.deleted_at = datetime.now(UTC)
        field.is_current = False
        await self.db.flush()

    async def get_geometry_geojson(self, field_id: UUID) -> dict | None:
        """Return the field's geometry as a GeoJSON dict."""
        from geoalchemy2.functions import ST_AsGeoJSON

        result = await self.db.execute(
            select(ST_AsGeoJSON(Field.geometry)).where(Field.id == field_id)
        )
        geojson_str = result.scalar_one_or_none()
        if geojson_str is None:
            return None
        return json.loads(geojson_str)

    # ── Internal helpers ───────────────────────────────────────────

    @staticmethod
    def _geojson_to_wkb_element(geojson: dict) -> str:
        """Convert a GeoJSON dict to a SQL expression for ST_GeomFromGeoJSON."""
        return func.ST_SetSRID(
            func.ST_GeomFromGeoJSON(json.dumps(geojson)),
            4326,
        )

    async def _update_area(self, field: Field) -> None:
        """Compute area in acres from geometry and update the field."""
        # ST_Area in SRID 4326 returns degrees², so transform to a meter-based CRS
        # Use ST_Area with geography cast for accurate area in m², then convert to acres
        result = await self.db.execute(
            select(func.ST_Area(cast(Field.geometry, Geography)) / 4046.8564224).where(
                Field.id == field.id
            )
        )
        area = result.scalar_one_or_none()
        if area is not None:
            field.area_acres = round(float(area), 2)
            await self.db.flush()

    async def _find_chain_root(self, field: Field) -> UUID:
        """Walk supersedes_id chain to find the root field ID."""
        current = field
        while current.supersedes_id is not None:
            result = await self.db.execute(select(Field).where(Field.id == current.supersedes_id))
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            current = parent
        return current.id

    async def _find_chain_root_field(self, field: Field) -> Field:
        """Walk supersedes_id chain to find the root Field object."""
        current = field
        while current.supersedes_id is not None:
            result = await self.db.execute(select(Field).where(Field.id == current.supersedes_id))
            parent = result.scalar_one_or_none()
            if parent is None:
                break
            current = parent
        return current
