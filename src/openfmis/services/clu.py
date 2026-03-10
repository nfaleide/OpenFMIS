"""CLUService — USDA Common Land Unit spatial queries."""

import json

from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.clu import CLU
from openfmis.models.field import Field


class CLUService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_clus_for_field(self, field_id: object) -> list[dict]:
        """Return all CLU polygons that intersect the given field's geometry."""
        # First get the field geometry
        field_result = await self.db.execute(
            select(Field).where(Field.id == field_id, Field.deleted_at.is_(None))
        )
        field = field_result.scalar_one_or_none()
        if field is None or field.geometry is None:
            return []

        result = await self.db.execute(
            select(CLU, ST_AsGeoJSON(CLU.geom).label("geojson"))
            .where(ST_Intersects(CLU.geom, Field.geometry))
            .where(Field.id == field_id)
            .join(Field, ST_Intersects(CLU.geom, Field.geometry))
            .where(Field.id == field_id, Field.deleted_at.is_(None))
        )
        return [_clu_dict(row.CLU, row.geojson) for row in result]

    async def get_clus_at_point(self, lon: float, lat: float, limit: int = 20) -> list[dict]:
        """Return CLU polygons containing the given point."""
        point_wkt = f"POINT({lon} {lat})"
        result = await self.db.execute(
            select(CLU, ST_AsGeoJSON(CLU.geom).label("geojson"))
            .where(
                ST_Intersects(
                    CLU.geom,
                    func.ST_SetSRID(func.ST_GeomFromText(point_wkt), 4326),
                )
            )
            .limit(limit)
        )
        return [_clu_dict(row.CLU, row.geojson) for row in result]

    async def get_clus_by_county(
        self,
        state: str,
        county_fips: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict], int]:
        """Return paginated CLUs for a state+county FIPS."""
        from sqlalchemy import func as sa_func

        count_result = await self.db.execute(
            select(sa_func.count())
            .select_from(CLU)
            .where(CLU.state == state.upper(), CLU.county_fips == county_fips)
        )
        total = count_result.scalar_one()

        result = await self.db.execute(
            select(CLU, ST_AsGeoJSON(CLU.geom).label("geojson"))
            .where(CLU.state == state.upper(), CLU.county_fips == county_fips)
            .offset(offset)
            .limit(limit)
        )
        return [_clu_dict(row.CLU, row.geojson) for row in result], total

    async def get_clus_intersecting_geometry(self, geojson: dict, limit: int = 200) -> list[dict]:
        """Return CLUs intersecting an arbitrary GeoJSON geometry."""
        import json as json_mod

        result = await self.db.execute(
            select(CLU, ST_AsGeoJSON(CLU.geom).label("geojson"))
            .where(
                ST_Intersects(
                    CLU.geom,
                    func.ST_SetSRID(func.ST_GeomFromGeoJSON(json_mod.dumps(geojson)), 4326),
                )
            )
            .limit(limit)
        )
        return [_clu_dict(row.CLU, row.geojson) for row in result]

    async def get_available_states(self) -> list[str]:
        result = await self.db.execute(select(CLU.state).distinct().order_by(CLU.state))
        return [row[0] for row in result]


def _clu_dict(clu: CLU, geojson: str | None) -> dict:
    return {
        "id": clu.id,
        "state": clu.state,
        "county_fips": clu.county_fips,
        "calcacres": clu.calcacres,
        "geom": json.loads(geojson) if geojson else None,
    }
