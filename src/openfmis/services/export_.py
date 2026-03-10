"""ExportService — export Fields to common vector formats.

Supported output formats:
  - GeoJSON FeatureCollection  (pure Python, no GDAL needed)
  - Shapefile (.zip)           (fiona)
  - KML                        (native XML — no GDAL KML driver required)
  - CSV                        (WKT geometry column)

All geometries are returned in WGS84 (EPSG:4326), the native storage CRS.
"""

import csv
import io
import json
import os
import tempfile
import zipfile
from uuid import UUID

import fiona
from geoalchemy2.functions import ST_AsGeoJSON
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.field import Field


class ExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def export_geojson(
        self,
        field_ids: list[UUID] | None = None,
        group_id: UUID | None = None,
    ) -> dict:
        """Return a GeoJSON FeatureCollection."""
        rows = await self._fetch_fields_with_geometry(field_ids, group_id)
        features = []
        for field, geojson_str in rows:
            geom = json.loads(geojson_str) if geojson_str else None
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": _field_properties(field),
                }
            )
        return {"type": "FeatureCollection", "features": features}

    async def export_shapefile(
        self,
        field_ids: list[UUID] | None = None,
        group_id: UUID | None = None,
    ) -> bytes:
        """Return a zip archive containing a shapefile."""
        rows = await self._fetch_fields_with_geometry(field_ids, group_id)

        schema = {
            "geometry": "MultiPolygon",
            "properties": {
                "id": "str",
                "name": "str",
                "group_id": "str",
                "area_acres": "float",
                "version": "int",
                "created_at": "str",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, "fields.shp")
            with fiona.open(
                shp_path, "w", driver="ESRI Shapefile", schema=schema, crs="EPSG:4326"
            ) as dst:
                for field, geojson_str in rows:
                    if not geojson_str:
                        continue
                    geom_dict = json.loads(geojson_str)
                    dst.write(
                        {
                            "geometry": geom_dict,
                            "properties": {
                                "id": str(field.id),
                                "name": field.name,
                                "group_id": str(field.group_id),
                                "area_acres": field.area_acres,
                                "version": field.version,
                                "created_at": field.created_at.isoformat(),
                            },
                        }
                    )

            # Zip the shapefile components
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(tmpdir):
                    zf.write(os.path.join(tmpdir, fname), fname)
            return zip_buf.getvalue()

    async def export_kml(
        self,
        field_ids: list[UUID] | None = None,
        group_id: UUID | None = None,
    ) -> bytes:
        """Return KML bytes (generated natively — no GDAL KML driver required)."""
        rows = await self._fetch_fields_with_geometry(field_ids, group_id)
        return _build_kml(rows)

    async def export_csv(
        self,
        field_ids: list[UUID] | None = None,
        group_id: UUID | None = None,
    ) -> str:
        """Return CSV string with WKT geometry column."""

        rows = await self._fetch_fields_with_geometry(field_ids, group_id)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id", "name", "group_id", "area_acres", "version", "created_at", "wkt"])

        for field, geojson_str in rows:
            if geojson_str:
                geom = shape(json.loads(geojson_str))
                wkt = geom.wkt
            else:
                wkt = ""
            writer.writerow(
                [
                    str(field.id),
                    field.name,
                    str(field.group_id),
                    field.area_acres,
                    field.version,
                    field.created_at.isoformat(),
                    wkt,
                ]
            )

        return buf.getvalue()

    # ── Internal helpers ───────────────────────────────────────────────────

    async def _fetch_fields_with_geometry(
        self,
        field_ids: list[UUID] | None,
        group_id: UUID | None,
    ) -> list[tuple[Field, str | None]]:
        """Return (Field, geojson_str | None) pairs for current, non-deleted fields."""
        query = (
            select(Field, ST_AsGeoJSON(Field.geometry).label("geojson"))
            .where(Field.deleted_at.is_(None))
            .where(Field.is_current.is_(True))
            .order_by(Field.name)
        )

        if field_ids is not None:
            query = query.where(Field.id.in_(field_ids))

        if group_id is not None:
            query = query.where(Field.group_id == group_id)

        result = await self.db.execute(query)
        return [(row.Field, row.geojson) for row in result]


def _build_kml(rows: list[tuple["Field", str | None]]) -> bytes:
    """Generate a KML document from field rows using Python's stdlib xml module."""
    import xml.etree.ElementTree as ET

    kml_ns = "http://www.opengis.net/kml/2.2"
    ET.register_namespace("", kml_ns)
    kml = ET.Element(f"{{{kml_ns}}}kml")
    doc = ET.SubElement(kml, f"{{{kml_ns}}}Document")

    for field, geojson_str in rows:
        if not geojson_str:
            continue
        pm = ET.SubElement(doc, f"{{{kml_ns}}}Placemark")
        ET.SubElement(pm, f"{{{kml_ns}}}name").text = field.name
        desc = f"Area: {field.area_acres} acres | Group: {field.group_id}"
        ET.SubElement(pm, f"{{{kml_ns}}}description").text = desc

        geom_dict = json.loads(geojson_str)
        _append_kml_geometry(pm, geom_dict, kml_ns)

    tree = ET.ElementTree(kml)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


def _append_kml_geometry(parent: object, geom: dict, ns: str) -> None:
    """Append KML geometry elements to a Placemark element."""
    import xml.etree.ElementTree as ET

    gtype = geom.get("type")
    coords = geom.get("coordinates", [])

    if gtype == "MultiPolygon":
        if len(coords) == 1:
            # Single-part MultiPolygon → emit as <Polygon>
            _append_kml_polygon(parent, coords[0], ns)  # type: ignore[arg-type]
        else:
            mg = ET.SubElement(parent, f"{{{ns}}}MultiGeometry")  # type: ignore[union-attr]
            for ring_set in coords:
                _append_kml_polygon(mg, ring_set, ns)
    elif gtype == "Polygon":
        _append_kml_polygon(parent, coords, ns)  # type: ignore[arg-type]


def _append_kml_polygon(parent: object, ring_set: list, ns: str) -> None:
    import xml.etree.ElementTree as ET

    poly = ET.SubElement(parent, f"{{{ns}}}Polygon")  # type: ignore[union-attr]
    if not ring_set:
        return
    outer = ET.SubElement(poly, f"{{{ns}}}outerBoundaryIs")
    lr = ET.SubElement(outer, f"{{{ns}}}LinearRing")
    ET.SubElement(lr, f"{{{ns}}}coordinates").text = _coords_to_kml(ring_set[0])

    for inner_ring in ring_set[1:]:
        inner = ET.SubElement(poly, f"{{{ns}}}innerBoundaryIs")
        lr_in = ET.SubElement(inner, f"{{{ns}}}LinearRing")
        ET.SubElement(lr_in, f"{{{ns}}}coordinates").text = _coords_to_kml(inner_ring)


def _coords_to_kml(ring: list) -> str:
    return " ".join(f"{lon},{lat},0" for lon, lat in ring)


def _field_properties(field: "Field") -> dict:
    return {
        "id": str(field.id),
        "name": field.name,
        "description": field.description,
        "group_id": str(field.group_id),
        "area_acres": field.area_acres,
        "version": field.version,
        "is_current": field.is_current,
        "created_at": field.created_at.isoformat(),
        "updated_at": field.updated_at.isoformat(),
    }
