"""PLSSService — Public Land Survey System search and lookup."""

import json

from geoalchemy2.functions import ST_AsGeoJSON, ST_Intersects
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.plss import PLSSSection, PLSSTownship


class PLSSService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def search_townships(
        self,
        q: str | None = None,
        state: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search townships by label, lndkey, or state.

        q can be a partial label like '2S 5E' or a lndkey prefix like 'ND06'.
        """
        query = select(PLSSTownship, ST_AsGeoJSON(PLSSTownship.geom).label("geojson"))

        filters = []
        if state:
            filters.append(PLSSTownship.state == state.upper())

        if q:
            q_clean = q.strip()
            filters.append(
                or_(
                    PLSSTownship.label.ilike(f"%{q_clean}%"),
                    PLSSTownship.lndkey.ilike(f"%{q_clean}%"),
                )
            )

        if filters:
            query = query.where(*filters)

        query = query.order_by(PLSSTownship.state, PLSSTownship.label).limit(limit)
        result = await self.db.execute(query)
        return [_township_dict(row.PLSSTownship, row.geojson) for row in result]

    async def get_township(self, township_id: int) -> dict | None:
        result = await self.db.execute(
            select(PLSSTownship, ST_AsGeoJSON(PLSSTownship.geom).label("geojson")).where(
                PLSSTownship.id == township_id
            )
        )
        row = result.first()
        if row is None:
            return None
        return _township_dict(row.PLSSTownship, row.geojson)

    async def get_sections_for_township(self, lndkey: str) -> list[dict]:
        """Return all sections within a township identified by its lndkey prefix."""
        result = await self.db.execute(
            select(PLSSSection, ST_AsGeoJSON(PLSSSection.geom).label("geojson"))
            .where(PLSSSection.lndkey.like(f"{lndkey}%"))
            .order_by(PLSSSection.sectn)
        )
        return [_section_dict(row.PLSSSection, row.geojson) for row in result]

    async def search_sections(
        self,
        q: str | None = None,
        state: str | None = None,
        mtrs: str | None = None,
        fips_c: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search sections by mtrs (meridian-township-range-section), label, state, or FIPS."""
        query = select(PLSSSection, ST_AsGeoJSON(PLSSSection.geom).label("geojson"))

        filters = []
        if state:
            # Extract state from lndkey prefix (first 2 chars)
            filters.append(PLSSSection.lndkey.ilike(f"{state.upper()}%"))
        if fips_c:
            filters.append(PLSSSection.fips_c == fips_c)
        if mtrs:
            filters.append(PLSSSection.mtrs.ilike(f"%{mtrs}%"))
        if q:
            filters.append(
                or_(
                    PLSSSection.mtrs.ilike(f"%{q}%"),
                    PLSSSection.label.ilike(f"%{q}%"),
                    PLSSSection.sectionkey.ilike(f"%{q}%"),
                )
            )

        if filters:
            query = query.where(*filters)

        query = query.order_by(PLSSSection.mtrs).limit(limit)
        result = await self.db.execute(query)
        return [_section_dict(row.PLSSSection, row.geojson) for row in result]

    async def get_section(self, section_id: int) -> dict | None:
        result = await self.db.execute(
            select(PLSSSection, ST_AsGeoJSON(PLSSSection.geom).label("geojson")).where(
                PLSSSection.id == section_id
            )
        )
        row = result.first()
        if row is None:
            return None
        return _section_dict(row.PLSSSection, row.geojson)

    async def find_sections_at_point(self, lon: float, lat: float) -> list[dict]:
        """Return sections containing the given point."""
        point_wkt = f"POINT({lon} {lat})"
        result = await self.db.execute(
            select(PLSSSection, ST_AsGeoJSON(PLSSSection.geom).label("geojson"))
            .where(
                ST_Intersects(
                    PLSSSection.geom,
                    func.ST_SetSRID(func.ST_GeomFromText(point_wkt), 4326),
                )
            )
            .limit(10)
        )
        return [_section_dict(row.PLSSSection, row.geojson) for row in result]

    async def find_townships_at_point(self, lon: float, lat: float) -> list[dict]:
        """Return townships containing the given point."""
        point_wkt = f"POINT({lon} {lat})"
        result = await self.db.execute(
            select(PLSSTownship, ST_AsGeoJSON(PLSSTownship.geom).label("geojson"))
            .where(
                ST_Intersects(
                    PLSSTownship.geom,
                    func.ST_SetSRID(func.ST_GeomFromText(point_wkt), 4326),
                )
            )
            .limit(5)
        )
        return [_township_dict(row.PLSSTownship, row.geojson) for row in result]

    async def get_available_states(self) -> list[str]:
        """Return sorted list of states present in the plss_townships table."""
        result = await self.db.execute(
            select(PLSSTownship.state)
            .where(PLSSTownship.state.isnot(None))
            .distinct()
            .order_by(PLSSTownship.state)
        )
        return [row[0] for row in result if row[0]]


# ── Serialisers ────────────────────────────────────────────────────────────


def _township_dict(t: PLSSTownship, geojson: str | None) -> dict:
    return {
        "id": t.id,
        "gid": t.gid,
        "lndkey": t.lndkey,
        "state": t.state,
        "town": t.town,
        "twndir": t.twndir,
        "range": t.range_,
        "rngdir": t.rngdir,
        "label": t.label,
        "source": t.source,
        "fips_c": t.fips_c,
        "geom": json.loads(geojson) if geojson else None,
    }


def _section_dict(s: PLSSSection, geojson: str | None) -> dict:
    return {
        "id": s.id,
        "gid": s.gid,
        "lndkey": s.lndkey,
        "section": s.sectn,
        "sectionkey": s.sectionkey,
        "label": s.label,
        "mtrs": s.mtrs,
        "source": s.source,
        "fips_c": s.fips_c,
        "geom": json.loads(geojson) if geojson else None,
    }
