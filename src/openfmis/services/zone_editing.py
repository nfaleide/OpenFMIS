"""ZoneEditingService — spatial operations on analysis zones.

Merge, shift breakpoints, recolor, paint, dissolve.
All geometry ops delegate to PostGIS functions.
"""

from __future__ import annotations

import json
import logging
import uuid

from geoalchemy2.functions import ST_AsGeoJSON, ST_Union
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import AnalysisZone

log = logging.getLogger(__name__)


class ZoneNotFoundError(Exception):
    pass


class ZoneEditingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def merge_zones(
        self, zone_ids: list[uuid.UUID], merged_name: str, created_by: uuid.UUID | None = None
    ) -> AnalysisZone:
        """Merge multiple zones into one via ST_Union. Original zones are deleted."""
        if len(zone_ids) < 2:
            raise ValueError("Need at least 2 zones to merge")

        zones = await self._load_zones(zone_ids)
        field_ids = {z.field_id for z in zones}
        if len(field_ids) != 1:
            raise ValueError("All zones must belong to the same field")
        field_id = field_ids.pop()

        # Compute ST_Union of all zone geometries
        result = await self.db.execute(
            select(ST_AsGeoJSON(ST_Union(AnalysisZone.geometry)).label("geojson")).where(
                AnalysisZone.id.in_(zone_ids)
            )
        )
        row = result.one()
        merged_geojson = json.loads(row.geojson) if row.geojson else None

        # Delete originals
        for z in zones:
            await self.db.delete(z)
        await self.db.flush()

        # Create merged zone
        merged = AnalysisZone(
            field_id=field_id,
            name=merged_name,
            geometry=f"SRID=4326;{_geojson_to_wkt_body(merged_geojson)}"
            if merged_geojson
            else None,
            created_by=created_by,
        )
        self.db.add(merged)
        await self.db.flush()
        await self.db.refresh(merged)
        return merged

    async def paint_zone(
        self,
        zone_id: uuid.UUID,
        paint_geometry: dict,
        created_by: uuid.UUID | None = None,
    ) -> AnalysisZone:
        """Add geometry to an existing zone via ST_Union with paint_geometry."""
        zone = await self._load_zone(zone_id)

        result = await self.db.execute(
            text("""
                SELECT ST_AsGeoJSON(
                    ST_Union(
                        az.geometry,
                        ST_GeomFromGeoJSON(:paint_geojson)::geometry
                    )
                ) AS geojson
                FROM analysis_zones az
                WHERE az.id = :zone_id
            """),
            {"zone_id": zone_id, "paint_geojson": json.dumps(paint_geometry)},
        )
        row = result.one()
        if row.geojson:
            geojson = json.loads(row.geojson)
            zone.geometry = f"SRID=4326;{_geojson_to_wkt_body(geojson)}"
        await self.db.flush()
        await self.db.refresh(zone)
        return zone

    async def dissolve_zones(self, zone_ids: list[uuid.UUID]) -> list[AnalysisZone]:
        """Dissolve internal boundaries between zones sharing edges.

        Returns the modified zones with updated geometries.
        """
        if len(zone_ids) < 2:
            raise ValueError("Need at least 2 zones to dissolve")

        zones = await self._load_zones(zone_ids)
        field_ids = {z.field_id for z in zones}
        if len(field_ids) != 1:
            raise ValueError("All zones must belong to the same field")

        # Compute the dissolved union
        result = await self.db.execute(
            select(ST_AsGeoJSON(ST_Union(AnalysisZone.geometry)).label("geojson")).where(
                AnalysisZone.id.in_(zone_ids)
            )
        )
        row = result.one()
        if not row.geojson:
            return zones

        dissolved_geojson = json.loads(row.geojson)

        # Apply dissolved geometry to the first zone, delete the rest
        keep = zones[0]
        keep.geometry = f"SRID=4326;{_geojson_to_wkt_body(dissolved_geojson)}"
        keep.name = f"{keep.name} (dissolved)"
        for z in zones[1:]:
            await self.db.delete(z)
        await self.db.flush()
        await self.db.refresh(keep)
        return [keep]

    async def split_zone(
        self,
        zone_id: uuid.UUID,
        split_line: dict,
        created_by: uuid.UUID | None = None,
    ) -> list[AnalysisZone]:
        """Split a zone into two parts using a LineString geometry (ST_Split)."""
        zone = await self._load_zone(zone_id)

        result = await self.db.execute(
            text("""
                SELECT ST_AsGeoJSON(geom) AS geojson
                FROM ST_Dump(
                    ST_Split(
                        (SELECT geometry FROM analysis_zones WHERE id = :zone_id),
                        ST_SetSRID(ST_GeomFromGeoJSON(:line), 4326)
                    )
                )
            """),
            {"zone_id": zone_id, "line": json.dumps(split_line)},
        )
        parts = [json.loads(row.geojson) for row in result if row.geojson]
        if len(parts) < 2:
            raise ValueError("Split line does not divide the zone into multiple parts")

        # Delete original
        field_id = zone.field_id
        base_name = zone.name
        await self.db.delete(zone)
        await self.db.flush()

        # Create new zones for each part
        new_zones = []
        for i, part_geojson in enumerate(parts):
            new_zone = AnalysisZone(
                field_id=field_id,
                name=f"{base_name} ({i + 1})",
                geometry=f"SRID=4326;{_geojson_to_wkt_body(part_geojson)}",
                created_by=created_by,
            )
            self.db.add(new_zone)
            new_zones.append(new_zone)
        await self.db.flush()
        for z in new_zones:
            await self.db.refresh(z)
        return new_zones

    async def buffer_zone(self, zone_id: uuid.UUID, distance_meters: float) -> AnalysisZone:
        """Buffer a zone geometry by distance_meters (positive = expand, negative = shrink)."""
        zone = await self._load_zone(zone_id)

        result = await self.db.execute(
            text("""
                SELECT ST_AsGeoJSON(
                    ST_Transform(
                        ST_Buffer(
                            ST_Transform(az.geometry, 3857),
                            :dist
                        ),
                        4326
                    )
                ) AS geojson
                FROM analysis_zones az
                WHERE az.id = :zone_id
            """),
            {"zone_id": zone_id, "dist": distance_meters},
        )
        row = result.one()
        if row.geojson:
            geojson = json.loads(row.geojson)
            zone.geometry = f"SRID=4326;{_geojson_to_wkt_body(geojson)}"
        await self.db.flush()
        await self.db.refresh(zone)
        return zone

    # ── Internal helpers ──────────────────────────────────────────────────

    async def _load_zone(self, zone_id: uuid.UUID) -> AnalysisZone:
        result = await self.db.execute(select(AnalysisZone).where(AnalysisZone.id == zone_id))
        zone = result.scalar_one_or_none()
        if zone is None:
            raise ZoneNotFoundError(str(zone_id))
        return zone

    async def _load_zones(self, zone_ids: list[uuid.UUID]) -> list[AnalysisZone]:
        result = await self.db.execute(select(AnalysisZone).where(AnalysisZone.id.in_(zone_ids)))
        zones = list(result.scalars().all())
        if len(zones) != len(zone_ids):
            found = {z.id for z in zones}
            missing = set(zone_ids) - found
            raise ZoneNotFoundError(f"Zones not found: {missing}")
        return zones


def _geojson_to_wkt_body(geojson: dict) -> str:
    """Convert GeoJSON geometry dict to WKT (without SRID prefix)."""
    geom_type = geojson.get("type", "")
    coords = geojson.get("coordinates", [])

    if geom_type == "Polygon":
        rings = []
        for ring in coords:
            ring_str = ", ".join(f"{x} {y}" for x, y in ring)
            rings.append(f"({ring_str})")
        return f"MULTIPOLYGON(({', '.join(rings)}))"

    if geom_type == "MultiPolygon":
        polys = []
        for poly in coords:
            rings = []
            for ring in poly:
                ring_str = ", ".join(f"{x} {y}" for x, y in ring)
                rings.append(f"({ring_str})")
            polys.append(f"({', '.join(rings)})")
        return f"MULTIPOLYGON({', '.join(polys)})"

    raise ValueError(f"Unsupported geometry type: {geom_type}")
