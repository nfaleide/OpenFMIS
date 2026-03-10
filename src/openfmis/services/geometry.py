"""GeometryService — PostGIS spatial operations."""

import json
from uuid import UUID

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.models.field import Field


class GeometryService:
    """Stateless spatial operations backed by PostGIS."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validation ─────────────────────────────────────────────────

    async def validate(self, geojson: dict) -> tuple[bool, str | None]:
        """Check if a GeoJSON geometry is valid. Returns (is_valid, reason)."""
        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        result = await self.db.execute(
            select(
                func.ST_IsValid(geom_expr),
                func.ST_IsValidReason(geom_expr),
            )
        )
        row = result.one()
        is_valid = row[0]
        reason = None if is_valid else row[1]
        return is_valid, reason

    # ── Area calculations ──────────────────────────────────────────

    async def calculate_area(self, geojson: dict) -> tuple[float, float]:
        """Calculate area in acres and square meters.

        Uses Geography cast for accurate geodesic area.
        Returns (area_acres, area_sq_meters).
        """
        from geoalchemy2 import Geography

        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        result = await self.db.execute(select(func.ST_Area(cast(geom_expr, Geography))))
        area_sq_m = float(result.scalar_one())
        area_acres = area_sq_m / 4046.8564224
        return round(area_acres, 2), round(area_sq_m, 2)

    async def calculate_bbox_area(self, geojson: dict) -> tuple[float, float, float, float, float]:
        """Calculate bounding box and its area.

        Returns (min_lon, min_lat, max_lon, max_lat, area_acres).
        """
        from geoalchemy2 import Geography

        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        envelope = func.ST_Envelope(geom_expr)

        result = await self.db.execute(
            select(
                func.ST_XMin(envelope),
                func.ST_YMin(envelope),
                func.ST_XMax(envelope),
                func.ST_YMax(envelope),
                func.ST_Area(cast(envelope, Geography)),
            )
        )
        row = result.one()
        min_lon, min_lat, max_lon, max_lat, bbox_area_m2 = (
            float(row[0]),
            float(row[1]),
            float(row[2]),
            float(row[3]),
            float(row[4]),
        )
        bbox_area_acres = round(bbox_area_m2 / 4046.8564224, 2)
        return min_lon, min_lat, max_lon, max_lat, bbox_area_acres

    # ── Geometry type info ─────────────────────────────────────────

    async def get_type(self, geojson: dict) -> tuple[str, int]:
        """Return (geometry_type, num_geometries)."""
        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        result = await self.db.execute(
            select(
                func.ST_GeometryType(geom_expr),
                func.ST_NumGeometries(geom_expr),
            )
        )
        row = result.one()
        # ST_GeometryType returns e.g. "ST_MultiPolygon", strip the "ST_" prefix
        geom_type = str(row[0]).replace("ST_", "").upper()
        num_geoms = int(row[1])
        return geom_type, num_geoms

    # ── Centroid ───────────────────────────────────────────────────

    async def centroid(self, geojson: dict) -> tuple[float, float]:
        """Return (longitude, latitude) of the centroid."""
        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        centroid_expr = func.ST_Centroid(geom_expr)
        result = await self.db.execute(select(func.ST_X(centroid_expr), func.ST_Y(centroid_expr)))
        row = result.one()
        return float(row[0]), float(row[1])

    # ── Merge / Union ──────────────────────────────────────────────

    async def union(self, geojsons: list[dict]) -> dict:
        """Union multiple geometries into one. Returns GeoJSON dict."""
        if len(geojsons) < 2:
            raise ValidationError("At least 2 geometries required for union")

        # Build a ST_Union aggregate over all input geometries
        geom_exprs = [
            func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(g)), 4326) for g in geojsons
        ]

        # Chain pairwise unions
        combined = geom_exprs[0]
        for geom in geom_exprs[1:]:
            combined = func.ST_Union(combined, geom)

        result = await self.db.execute(select(func.ST_AsGeoJSON(combined)))
        return json.loads(result.scalar_one())

    # ── Clip / Intersection ────────────────────────────────────────

    async def clip(self, geojson: dict, clip_geojson: dict) -> dict:
        """Clip geometry by another. Returns the intersection as GeoJSON."""
        geom_a = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        geom_b = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(clip_geojson)), 4326)

        result = await self.db.execute(
            select(func.ST_AsGeoJSON(func.ST_Intersection(geom_a, geom_b)))
        )
        geojson_str = result.scalar_one()
        return json.loads(geojson_str)

    # ── Hole / Symmetric Difference ────────────────────────────────

    async def hole(self, geojson: dict, hole_geojson: dict) -> dict:
        """Punch a hole: symmetric difference. Returns GeoJSON."""
        geom_a = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        geom_b = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(hole_geojson)), 4326)

        result = await self.db.execute(
            select(func.ST_AsGeoJSON(func.ST_Difference(geom_a, geom_b)))
        )
        return json.loads(result.scalar_one())

    # ── Buffer ─────────────────────────────────────────────────────

    async def buffer(self, geojson: dict, distance_meters: float) -> dict:
        """Buffer a geometry by distance in meters. Returns GeoJSON.

        Uses Geography cast for accurate distance-based buffer.
        """
        from geoalchemy2 import Geography

        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)
        # Cast to geography for meter-based buffer, then back to geometry for GeoJSON
        buffered = func.ST_Buffer(cast(geom_expr, Geography), distance_meters)
        result = await self.db.execute(select(func.ST_AsGeoJSON(buffered)))
        return json.loads(result.scalar_one())

    # ── Spatial queries against stored fields ──────────────────────

    async def find_intersecting_fields(
        self,
        geojson: dict,
        group_id: UUID | None = None,
    ) -> list[dict]:
        """Find all current fields that intersect the given geometry.

        Returns list of dicts with field_id, field_name, intersection_area_acres, overlap_percent.
        """
        from geoalchemy2 import Geography

        geom_expr = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geojson)), 4326)

        query = select(
            Field.id,
            Field.name,
            # Intersection area in acres
            (
                func.ST_Area(cast(func.ST_Intersection(Field.geometry, geom_expr), Geography))
                / 4046.8564224
            ).label("intersection_acres"),
            # Overlap percent: intersection / query geometry area * 100
            (
                func.ST_Area(cast(func.ST_Intersection(Field.geometry, geom_expr), Geography))
                / func.nullif(func.ST_Area(cast(geom_expr, Geography)), 0)
                * 100
            ).label("overlap_pct"),
        ).where(
            Field.geometry.isnot(None),
            Field.is_current.is_(True),
            Field.deleted_at.is_(None),
            func.ST_Intersects(Field.geometry, geom_expr),
        )

        if group_id is not None:
            query = query.where(Field.group_id == group_id)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            {
                "field_id": row[0],
                "field_name": row[1],
                "intersection_area_acres": round(float(row[2]), 2) if row[2] else None,
                "overlap_percent": round(float(row[3]), 2) if row[3] else None,
            }
            for row in rows
        ]
