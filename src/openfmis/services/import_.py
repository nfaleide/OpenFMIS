"""ImportService — vector file ingestion into Fields.

Supported formats (auto-detected from filename extension):
  - Shapefile    (.zip containing .shp/.dbf/.shx/.prj)
  - GeoJSON      (.geojson, .json)
  - KML          (.kml)
  - CSV          (.csv) with WKT column or lat/lon columns

All geometries are normalised to MULTIPOLYGON SRID 4326 before insert.
Non-polygon geometry types (points, lines) are skipped.
Source CRS is reprojected to WGS84 via fiona.transform.transform_geom.
"""

import csv
import io
import os
import tempfile
import zipfile
from uuid import UUID

import fiona
import fiona.transform
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.schemas.field import FieldCreate
from openfmis.schemas.import_ import ImportResult
from openfmis.services.field import FieldService

# Attribute names commonly used as field/parcel names in ag shapefiles
_NAME_CANDIDATES = (
    "name",
    "field_name",
    "fieldname",
    "field",
    "label",
    "parcel",
    "tract",
    "description",
    "farm_name",
    "farmname",
    "objectid",
    "fid",
)

_WKT_CANDIDATES = ("wkt", "geometry", "geom", "shape", "wkt_geom", "the_geom")
_LAT_CANDIDATES = ("latitude", "lat", "y", "ylat")
_LON_CANDIDATES = ("longitude", "lon", "long", "x", "xlong", "xlon")


class ImportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def import_vector(
        self,
        file_content: bytes,
        filename: str,
        group_id: UUID,
        created_by: UUID | None = None,
        name_field: str | None = None,
    ) -> ImportResult:
        """Parse a vector file and bulk-create Field records.

        Returns an ImportResult summarising what was created/skipped.
        """
        ext = os.path.splitext(filename.lower())[1]

        if ext == ".zip":
            return await self._import_shapefile(file_content, group_id, created_by, name_field)
        elif ext in (".geojson", ".json"):
            return await self._import_geojson(file_content, group_id, created_by, name_field)
        elif ext == ".kml":
            return await self._import_kml(file_content, group_id, created_by, name_field)
        elif ext == ".csv":
            return await self._import_csv(file_content, group_id, created_by, name_field)
        else:
            return ImportResult(
                created=0,
                skipped=0,
                errors=[
                    f"Unsupported file type: {ext!r}. Accepted: .zip, .geojson, .json, .kml, .csv"
                ],
                field_ids=[],
            )

    # ── Format handlers ────────────────────────────────────────────────────

    async def _import_shapefile(
        self,
        zip_bytes: bytes,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
    ) -> ImportResult:
        """Extract zip → open with fiona → create fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(zip_bytes)

            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(tmpdir)
            except zipfile.BadZipFile:
                return ImportResult(
                    created=0,
                    skipped=0,
                    errors=["Uploaded file is not a valid zip archive."],
                    field_ids=[],
                )

            # Find the .shp file (may be nested in a subfolder)
            shp_path: str | None = None
            for root, _dirs, files in os.walk(tmpdir):
                for fname in files:
                    if fname.endswith(".shp"):
                        shp_path = os.path.join(root, fname)
                        break
                if shp_path:
                    break

            if shp_path is None:
                return ImportResult(
                    created=0,
                    skipped=0,
                    errors=["No .shp file found inside the uploaded zip."],
                    field_ids=[],
                )

            return await self._import_fiona_source(shp_path, group_id, created_by, name_field)

    async def _import_geojson(
        self,
        content: bytes,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
    ) -> ImportResult:
        # fiona can open GeoJSON from a virtual in-memory path via MemoryFile
        with fiona.MemoryFile(content) as memfile:
            with memfile.open() as src:
                return await self._read_fiona_features(src, group_id, created_by, name_field)

    async def _import_kml(
        self,
        content: bytes,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
    ) -> ImportResult:
        """Parse KML natively via ElementTree — extracts Polygon/MultiGeometry placemarks."""
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(content.decode("utf-8"))
        except ET.ParseError as exc:
            return ImportResult(created=0, skipped=0, errors=[f"Invalid KML: {exc}"], field_ids=[])

        # KML namespace is commonly http://www.opengis.net/kml/2.2 or no namespace
        ns_match = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        ns = f"{{{ns_match}}}" if ns_match else ""

        placemarks = root.iter(f"{ns}Placemark")
        svc = FieldService(self.db)
        created = 0
        skipped = 0
        errors: list[str] = []
        field_ids: list[UUID] = []

        for i, pm in enumerate(placemarks, start=1):
            try:
                name_el = pm.find(f"{ns}name")
                name = (name_el.text or "").strip() if name_el is not None else f"Field {i}"
                if not name:
                    name = f"Field {i}"

                geom = _parse_kml_geometry(pm, ns)
                if geom is None:
                    skipped += 1
                    errors.append(f"Placemark {i} ({name!r}): no polygon geometry — skipped")
                    continue

                mp_geojson = _to_multipolygon_geojson(geom)
                if mp_geojson is None:
                    skipped += 1
                    continue

                field = await svc.create_field(
                    FieldCreate(name=name, group_id=group_id, geometry_geojson=mp_geojson),
                    created_by=created_by,
                )
                field_ids.append(field.id)
                created += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                errors.append(f"Placemark {i}: {exc}")

        return ImportResult(created=created, skipped=skipped, errors=errors, field_ids=field_ids)

    async def _import_csv(
        self,
        content: bytes,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
    ) -> ImportResult:
        """CSV with either a WKT geometry column or separate lat/lon columns."""
        from shapely import wkt as shapely_wkt

        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return ImportResult(
                created=0, skipped=0, errors=["CSV has no header row."], field_ids=[]
            )

        fields_lower = {c.lower(): c for c in reader.fieldnames}

        # Detect geometry column strategy
        wkt_col: str | None = None
        lat_col: str | None = None
        lon_col: str | None = None
        for cand in _WKT_CANDIDATES:
            if cand in fields_lower:
                wkt_col = fields_lower[cand]
                break
        if wkt_col is None:
            for cand in _LAT_CANDIDATES:
                if cand in fields_lower:
                    lat_col = fields_lower[cand]
                    break
            for cand in _LON_CANDIDATES:
                if cand in fields_lower:
                    lon_col = fields_lower[cand]
                    break

        if wkt_col is None and (lat_col is None or lon_col is None):
            return ImportResult(
                created=0,
                skipped=0,
                errors=[
                    "CSV must have a WKT geometry column (wkt/geometry/geom/shape) "
                    "or lat/lon columns."
                ],
                field_ids=[],
            )

        # Detect name column
        resolved_name_col: str | None = None
        if name_field and name_field.lower() in fields_lower:
            resolved_name_col = fields_lower[name_field.lower()]
        else:
            for cand in _NAME_CANDIDATES:
                if cand in fields_lower:
                    resolved_name_col = fields_lower[cand]
                    break

        svc = FieldService(self.db)
        created = 0
        skipped = 0
        errors: list[str] = []
        field_ids: list[UUID] = []

        for i, row in enumerate(reader, start=2):  # row 1 = header
            try:
                if wkt_col:
                    raw = row.get(wkt_col, "").strip()
                    if not raw:
                        skipped += 1
                        continue
                    geom = shapely_wkt.loads(raw)
                else:
                    lat_val = row.get(lat_col or "", "").strip()  # type: ignore[arg-type]
                    lon_val = row.get(lon_col or "", "").strip()  # type: ignore[arg-type]
                    if not lat_val or not lon_val:
                        skipped += 1
                        continue
                    # Point CSV — create a tiny buffered polygon (~1m radius)
                    from shapely.geometry import Point

                    pt = Point(float(lon_val), float(lat_val))
                    geom = pt.buffer(0.00001)  # ~1m in degrees

                mp_geojson = _to_multipolygon_geojson(geom)
                if mp_geojson is None:
                    skipped += 1
                    errors.append(f"Row {i}: unsupported geometry type {type(geom).__name__}")
                    continue

                name = _extract_name(row, resolved_name_col, i)
                field = await svc.create_field(
                    FieldCreate(name=name, group_id=group_id, geometry_geojson=mp_geojson),
                    created_by=created_by,
                )
                field_ids.append(field.id)
                created += 1
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                errors.append(f"Row {i}: {exc}")

        return ImportResult(created=created, skipped=skipped, errors=errors, field_ids=field_ids)

    # ── Fiona helpers ──────────────────────────────────────────────────────

    async def _import_fiona_source(
        self,
        path: str,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
        driver: str | None = None,
    ) -> ImportResult:
        kwargs: dict = {}
        if driver:
            kwargs["driver"] = driver
        with fiona.open(path, **kwargs) as src:
            return await self._read_fiona_features(src, group_id, created_by, name_field)

    async def _read_fiona_features(
        self,
        src: fiona.Collection,
        group_id: UUID,
        created_by: UUID | None,
        name_field: str | None,
    ) -> ImportResult:
        svc = FieldService(self.db)
        src_crs = src.crs_wkt or "EPSG:4326"
        needs_reproject = not _is_wgs84(src.crs)

        # Resolve name field from schema
        schema_props = list(src.schema.get("properties", {}).keys())
        resolved_name_field = _resolve_name_field(schema_props, name_field)

        created = 0
        skipped = 0
        errors: list[str] = []
        field_ids: list[UUID] = []

        for i, feature in enumerate(src, start=1):
            try:
                geom_dict = feature.geometry
                if geom_dict is None:
                    skipped += 1
                    continue

                # Reproject to WGS84 if needed
                if needs_reproject:
                    geom_dict = fiona.transform.transform_geom(src_crs, "EPSG:4326", geom_dict)

                geom = shape(geom_dict)
                mp_geojson = _to_multipolygon_geojson(geom)
                if mp_geojson is None:
                    skipped += 1
                    errors.append(
                        f"Feature {i}: unsupported geometry type {geom_dict.get('type')} — skipped"
                    )
                    continue

                props = dict(feature.properties or {})
                name = _extract_name(props, resolved_name_field, i)

                field = await svc.create_field(
                    FieldCreate(name=name, group_id=group_id, geometry_geojson=mp_geojson),
                    created_by=created_by,
                )
                field_ids.append(field.id)
                created += 1

            except Exception as exc:  # noqa: BLE001
                skipped += 1
                errors.append(f"Feature {i}: {exc}")

        return ImportResult(created=created, skipped=skipped, errors=errors, field_ids=field_ids)


# ── Module-level geometry helpers ──────────────────────────────────────────


def _to_multipolygon_geojson(geom: object) -> dict | None:
    """Normalise any shapely geometry to a MultiPolygon GeoJSON dict.

    Returns None if the geometry type can't be represented as a polygon
    (e.g. bare Point or LineString without a buffer step).
    """
    if isinstance(geom, Polygon):
        geom = MultiPolygon([geom])
    elif not isinstance(geom, MultiPolygon):
        # Attempt to extract polygons from a GeometryCollection
        from shapely.geometry import GeometryCollection

        if isinstance(geom, GeometryCollection):
            polys = [g for g in geom.geoms if isinstance(g, (Polygon, MultiPolygon))]
            if not polys:
                return None
            from shapely.ops import unary_union

            geom = unary_union(polys)
            if isinstance(geom, Polygon):
                geom = MultiPolygon([geom])
            elif not isinstance(geom, MultiPolygon):
                return None
        else:
            return None

    if not isinstance(geom, MultiPolygon) or geom.is_empty:
        return None

    return mapping(geom)  # type: ignore[return-value]


def _is_wgs84(crs: object) -> bool:
    """Return True if the fiona CRS object is WGS84 / EPSG:4326."""
    if crs is None:
        return True  # assume WGS84 if unspecified
    crs_str = str(crs).upper()
    return "EPSG:4326" in crs_str or "WGS84" in crs_str or "WGS 84" in crs_str


def _resolve_name_field(schema_props: list[str], hint: str | None) -> str | None:
    """Pick the best name attribute from the feature schema."""
    props_lower = {p.lower(): p for p in schema_props}
    if hint and hint.lower() in props_lower:
        return props_lower[hint.lower()]
    for cand in _NAME_CANDIDATES:
        if cand in props_lower:
            return props_lower[cand]
    return None


def _extract_name(props: dict, name_col: str | None, index: int) -> str:
    """Get a display name from feature properties, falling back to 'Field N'."""
    if name_col and name_col in props:
        val = props[name_col]
        if val is not None:
            return str(val).strip() or f"Field {index}"
    return f"Field {index}"


def _parse_kml_coords(coords_text: str) -> list[tuple[float, float]]:
    """Parse a KML <coordinates> string into (lon, lat) tuples."""
    ring = []
    for token in coords_text.strip().split():
        parts = token.split(",")
        if len(parts) >= 2:
            ring.append((float(parts[0]), float(parts[1])))
    return ring


def _parse_kml_polygon(el: object, ns: str) -> "Polygon | None":
    """Extract a shapely Polygon from a KML <Polygon> element."""
    from shapely.geometry import Polygon

    outer = el.find(f"{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")  # type: ignore[union-attr]
    if outer is None or not outer.text:
        return None
    exterior = _parse_kml_coords(outer.text)

    holes = []
    for inner in el.findall(f"{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates"):  # type: ignore[union-attr]
        if inner.text:
            holes.append(_parse_kml_coords(inner.text))

    try:
        return Polygon(exterior, holes)
    except Exception:  # noqa: BLE001
        return None


def _parse_kml_geometry(placemark: object, ns: str) -> "MultiPolygon | Polygon | None":
    """Extract polygon geometry from a KML Placemark element."""
    from shapely.geometry import MultiPolygon

    # Direct Polygon
    poly_el = placemark.find(f"{ns}Polygon")  # type: ignore[union-attr]
    if poly_el is not None:
        return _parse_kml_polygon(poly_el, ns)

    # MultiGeometry containing Polygons
    mg_el = placemark.find(f"{ns}MultiGeometry")  # type: ignore[union-attr]
    if mg_el is not None:
        polys = []
        for p_el in mg_el.findall(f"{ns}Polygon"):
            p = _parse_kml_polygon(p_el, ns)
            if p is not None:
                polys.append(p)
        if polys:
            return MultiPolygon(polys)

    return None
