"""Point ingestion service — file preview, upload with cleaning, structured intake."""

from __future__ import annotations

import csv
import io
import os
import tempfile
import zipfile
from datetime import date
from typing import Any
from uuid import UUID

import fiona
import numpy as np
from shapely.geometry import shape
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.point_dataset import PointCleaningLog, PointDataset
from openfmis.schemas.point_ingestion import CleaningRuleSpec, FilePreviewOut

# ── Column auto-detection patterns ──────────────────────────────────────────

_LAT_PATTERNS = {"latitude", "lat", "y", "ylat", "point_y", "lat_dd"}
_LON_PATTERNS = {"longitude", "lon", "long", "x", "xlong", "xlon", "point_x", "lon_dd"}
_YIELD_PATTERNS = {"yld_vol_dr", "yld_mass_d", "yield", "dry_yield", "wet_yield", "bu_ac", "bu/ac"}
_APPLIED_PATTERNS = {
    "rate",
    "rt_apd_ct",
    "rt_apd_ms",
    "applied_rate",
    "app_rate",
    "product_ra",
    "rate_actual",
}
_SOIL_PATTERNS = {
    "p_ppm",
    "k_ppm",
    "om_pct",
    "ph",
    "cec",
    "no3",
    "so4",
    "zn",
    "mn",
    "fe",
    "cu",
    "ca",
    "mg",
    "na",
    "b",
}
_EC_PATTERNS = {"ec_0_12", "ec_12_24", "ec_shallow", "ec_deep", "em_h", "em_v"}

_TYPE_PATTERNS: dict[str, set[str]] = {
    "soil_test": _SOIL_PATTERNS,
    "yield": _YIELD_PATTERNS,
    "as_applied_fert": _APPLIED_PATTERNS,
    "as_applied_chem": _APPLIED_PATTERNS,
    "ec_em": _EC_PATTERNS,
}


def _detect_column(columns_lower: dict[str, str], patterns: set[str]) -> str | None:
    for p in patterns:
        if p in columns_lower:
            return columns_lower[p]
    return None


def _suggest_type(columns_lower: set[str]) -> str | None:
    for dtype, patterns in _TYPE_PATTERNS.items():
        if columns_lower & patterns:
            return dtype
    return None


def _suggest_value_column(columns_lower: dict[str, str], dtype: str | None) -> str | None:
    if dtype and dtype in _TYPE_PATTERNS:
        return _detect_column(columns_lower, _TYPE_PATTERNS[dtype])
    return None


class PointIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Preview ─────────────────────────────────────────────────────

    async def preview_file(
        self,
        file_content: bytes,
        filename: str,
    ) -> FilePreviewOut:
        """Parse file and return column info + sample rows."""
        ext = os.path.splitext(filename.lower())[1]

        if ext == ".csv":
            return self._preview_csv(file_content)
        elif ext == ".xlsx":
            return self._preview_xlsx(file_content)
        elif ext in (".geojson", ".json"):
            return self._preview_geojson(file_content)
        elif ext == ".zip":
            return self._preview_shapefile(file_content)
        elif ext in (".gpkg",):
            return self._preview_gpkg(file_content)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _preview_csv(self, content: bytes) -> FilePreviewOut:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        all_columns = list(reader.fieldnames)
        cols_lower = {c.lower(): c for c in all_columns}

        lat_col = _detect_column(cols_lower, _LAT_PATTERNS)
        lon_col = _detect_column(cols_lower, _LON_PATTERNS)
        geometry_type = "latlon" if lat_col and lon_col else "unknown"

        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) >= 5:
                break

        non_coord = {c for c in all_columns if c.lower() not in _LAT_PATTERNS | _LON_PATTERNS}
        value_columns = sorted(non_coord)
        suggested_type = _suggest_type(set(cols_lower.keys()))
        suggested_value = _suggest_value_column(cols_lower, suggested_type)

        return FilePreviewOut(
            lat_column=lat_col,
            lon_column=lon_col,
            geometry_type=geometry_type,
            all_columns=all_columns,
            value_columns=value_columns,
            suggested_type=suggested_type,
            suggested_value_column=suggested_value,
            row_count=len(rows) + sum(1 for _ in reader),
            sample_rows=rows,
            crs="EPSG:4326",
        )

    def _preview_xlsx(self, content: bytes) -> FilePreviewOut:
        try:
            import openpyxl
        except ImportError:
            raise ValueError("openpyxl is required for XLSX preview")

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if not header:
            raise ValueError("XLSX has no header row")

        all_columns = [str(c) for c in header if c is not None]
        cols_lower = {c.lower(): c for c in all_columns}
        lat_col = _detect_column(cols_lower, _LAT_PATTERNS)
        lon_col = _detect_column(cols_lower, _LON_PATTERNS)

        sample_rows = []
        total = 0
        for row_vals in rows_iter:
            total += 1
            if len(sample_rows) < 5:
                sample_rows.append(dict(zip(all_columns, row_vals)))

        non_coord = {c for c in all_columns if c.lower() not in _LAT_PATTERNS | _LON_PATTERNS}
        suggested_type = _suggest_type(set(cols_lower.keys()))

        return FilePreviewOut(
            lat_column=lat_col,
            lon_column=lon_col,
            geometry_type="latlon" if lat_col and lon_col else "unknown",
            all_columns=all_columns,
            value_columns=sorted(non_coord),
            suggested_type=suggested_type,
            suggested_value_column=_suggest_value_column(cols_lower, suggested_type),
            row_count=total,
            sample_rows=sample_rows,
            crs="EPSG:4326",
        )

    def _preview_geojson(self, content: bytes) -> FilePreviewOut:
        with fiona.MemoryFile(content) as memfile:
            with memfile.open() as src:
                return self._preview_fiona(src)

    def _preview_shapefile(self, content: bytes) -> FilePreviewOut:
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "upload.zip")
            with open(zip_path, "wb") as f:
                f.write(content)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.filename.startswith("/") or ".." in member.filename:
                        raise ValueError("Zip archive contains unsafe paths")
                zf.extractall(tmpdir)
            shp_path = None
            for root, _, files in os.walk(tmpdir):
                for fname in files:
                    if fname.endswith(".shp"):
                        shp_path = os.path.join(root, fname)
                        break
                if shp_path:
                    break
            if not shp_path:
                raise ValueError("No .shp file found in zip")
            with fiona.open(shp_path) as src:
                return self._preview_fiona(src)

    def _preview_gpkg(self, content: bytes) -> FilePreviewOut:
        with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            with fiona.open(tmp_path) as src:
                return self._preview_fiona(src)
        finally:
            os.unlink(tmp_path)

    def _preview_fiona(self, src: fiona.Collection) -> FilePreviewOut:
        schema_props = list(src.schema.get("properties", {}).keys())
        cols_lower = {c.lower(): c for c in schema_props}
        sample_rows = []
        total = 0
        for feat in src:
            total += 1
            if len(sample_rows) < 5:
                row = dict(feat.properties or {})
                if feat.geometry:
                    geom = shape(feat.geometry)
                    row["_lat"] = geom.centroid.y
                    row["_lon"] = geom.centroid.x
                sample_rows.append(row)

        suggested_type = _suggest_type(set(cols_lower.keys()))

        return FilePreviewOut(
            lat_column=None,
            lon_column=None,
            geometry_type="geometry",
            all_columns=schema_props,
            value_columns=schema_props,
            suggested_type=suggested_type,
            suggested_value_column=_suggest_value_column(cols_lower, suggested_type),
            row_count=total,
            sample_rows=sample_rows,
            crs=str(src.crs_wkt or "EPSG:4326"),
        )

    # ── Upload with cleaning ───────────────────────────────────────

    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        field_id: UUID,
        dataset_type: str,
        label: str,
        value_column: str | None = None,
        unit: str | None = None,
        crop_year_id: UUID | None = None,
        sample_date: date | None = None,
        lat_column: str | None = None,
        lon_column: str | None = None,
        cleaning_rules: list[CleaningRuleSpec] | None = None,
    ) -> PointDataset:
        """Ingest a point file, apply cleaning rules, create PointDataset."""
        ext = os.path.splitext(filename.lower())[1]

        if ext == ".csv":
            points, raw_count = self._parse_csv_points(
                file_content,
                lat_column,
                lon_column,
                value_column,
            )
        else:
            points, raw_count = self._parse_geospatial_points(
                file_content,
                filename,
                value_column,
            )

        clean_count = raw_count
        cleaning_logs: list[dict[str, Any]] = []

        if cleaning_rules:
            for rule in cleaning_rules:
                before = len(points)
                points = self._apply_cleaning_rule(points, rule, value_column)
                removed = before - len(points)
                clean_count -= removed
                cleaning_logs.append(
                    {
                        "rule_type": rule.type,
                        "parameters": rule.parameters,
                        "points_removed": removed,
                    }
                )

        ds = PointDataset(
            field_id=field_id,
            crop_year_id=crop_year_id,
            dataset_type=dataset_type,
            label=label,
            value_column=value_column,
            unit=unit,
            sample_date=sample_date,
            source_file=filename,
            raw_count=raw_count,
            clean_count=clean_count,
        )
        self.db.add(ds)
        await self.db.flush()

        for log in cleaning_logs:
            cl = PointCleaningLog(
                dataset_id=ds.id,
                rule_type=log["rule_type"],
                parameters=log["parameters"],
                points_removed=log["points_removed"],
            )
            self.db.add(cl)
        await self.db.flush()
        await self.db.refresh(ds)
        return ds

    # ── Structured intake ──────────────────────────────────────────

    async def structured_intake(
        self,
        field_id: UUID,
        dataset_type: str,
        label: str,
        features: list[dict[str, Any]],
        value_column: str | None = None,
        unit: str | None = None,
        crop_year_id: UUID | None = None,
        sample_date: date | None = None,
        cleaning_log: list[dict[str, Any]] | None = None,
    ) -> PointDataset:
        """Create dataset from pre-parsed GeoJSON features (e.g. from QGIS)."""
        raw_count = len(features)
        clean_count = raw_count
        if cleaning_log:
            for entry in cleaning_log:
                clean_count -= entry.get("points_removed", 0)

        ds = PointDataset(
            field_id=field_id,
            crop_year_id=crop_year_id,
            dataset_type=dataset_type,
            label=label,
            value_column=value_column,
            unit=unit,
            sample_date=sample_date,
            raw_count=raw_count,
            clean_count=max(0, clean_count),
        )
        self.db.add(ds)
        await self.db.flush()

        if cleaning_log:
            for entry in cleaning_log:
                cl = PointCleaningLog(
                    dataset_id=ds.id,
                    rule_type=entry["rule_type"],
                    parameters=entry.get("parameters"),
                    points_removed=entry.get("points_removed", 0),
                )
                self.db.add(cl)
            await self.db.flush()

        await self.db.refresh(ds)
        return ds

    # ── Internal parsers ───────────────────────────────────────────

    def _parse_csv_points(
        self,
        content: bytes,
        lat_col: str | None,
        lon_col: str | None,
        value_col: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        if not lat_col or not lon_col:
            cols_lower = {c.lower(): c for c in reader.fieldnames}
            lat_col = lat_col or _detect_column(cols_lower, _LAT_PATTERNS)
            lon_col = lon_col or _detect_column(cols_lower, _LON_PATTERNS)
        if not lat_col or not lon_col:
            raise ValueError("Could not detect lat/lon columns")

        max_rows = 500_000
        points = []
        for row in reader:
            if len(points) >= max_rows:
                raise ValueError(
                    f"CSV exceeds maximum of {max_rows:,} rows. "
                    "Split the file into smaller batches."
                )
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                val = float(row[value_col]) if value_col and row.get(value_col) else None
                points.append({"lat": lat, "lon": lon, "value": val, "_raw": row})
            except (ValueError, KeyError):
                continue

        return points, len(points)

    def _parse_geospatial_points(
        self,
        content: bytes,
        filename: str,
        value_col: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        ext = os.path.splitext(filename.lower())[1]
        points: list[dict[str, Any]] = []

        if ext in (".geojson", ".json"):
            with fiona.MemoryFile(content) as memfile:
                with memfile.open() as src:
                    points = self._fiona_to_points(src, value_col)
        elif ext == ".zip":
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = os.path.join(tmpdir, "upload.zip")
                with open(zip_path, "wb") as f:
                    f.write(content)
                with zipfile.ZipFile(zip_path) as zf:
                    for member in zf.infolist():
                        if member.filename.startswith("/") or ".." in member.filename:
                            raise ValueError("Zip archive contains unsafe paths")
                    zf.extractall(tmpdir)
                for root, _, files in os.walk(tmpdir):
                    for fname in files:
                        if fname.endswith(".shp"):
                            with fiona.open(os.path.join(root, fname)) as src:
                                points = self._fiona_to_points(src, value_col)
                            break
        elif ext == ".gpkg":
            with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                with fiona.open(tmp_path) as src:
                    points = self._fiona_to_points(src, value_col)
            finally:
                os.unlink(tmp_path)

        return points, len(points)

    def _fiona_to_points(
        self,
        src: fiona.Collection,
        value_col: str | None,
    ) -> list[dict[str, Any]]:
        points = []
        for feat in src:
            if feat.geometry is None:
                continue
            geom = shape(feat.geometry)
            centroid = geom.centroid
            val = None
            if value_col and feat.properties:
                raw = feat.properties.get(value_col)
                try:
                    val = float(raw) if raw is not None else None
                except (ValueError, TypeError):
                    val = None
            points.append(
                {
                    "lat": centroid.y,
                    "lon": centroid.x,
                    "value": val,
                    "_raw": dict(feat.properties or {}),
                }
            )
        return points

    # ── Cleaning rules ─────────────────────────────────────────────

    def _apply_cleaning_rule(
        self,
        points: list[dict[str, Any]],
        rule: CleaningRuleSpec,
        value_col: str | None,
    ) -> list[dict[str, Any]]:
        if rule.type == "iqr":
            return self._clean_iqr(points, rule.parameters.get("factor", 1.5))
        elif rule.type == "stddev":
            return self._clean_stddev(points, rule.parameters.get("sigma", 2.5))
        elif rule.type == "percentile":
            return self._clean_percentile(
                points,
                rule.parameters.get("lower", 2.5),
                rule.parameters.get("upper", 97.5),
            )
        elif rule.type == "minmax":
            return self._clean_minmax(
                points,
                rule.parameters.get("min", 0),
                rule.parameters.get("max", 999999),
            )
        elif rule.type == "spatial_dedup":
            return self._clean_spatial_dedup(points, rule.parameters.get("distance_m", 1.0))
        elif rule.type == "edge_buffer":
            return self._clean_edge_buffer(points, rule.parameters.get("meters", 10))
        return points

    def _clean_iqr(self, points: list[dict], factor: float) -> list[dict]:
        values = [p["value"] for p in points if p.get("value") is not None]
        if len(values) < 4:
            return points
        arr = np.array(values)
        q1, q3 = np.percentile(arr, 25), np.percentile(arr, 75)
        iqr = q3 - q1
        lo, hi = q1 - factor * iqr, q3 + factor * iqr
        return [p for p in points if p.get("value") is None or lo <= p["value"] <= hi]

    def _clean_stddev(self, points: list[dict], sigma: float) -> list[dict]:
        values = [p["value"] for p in points if p.get("value") is not None]
        if len(values) < 3:
            return points
        arr = np.array(values)
        mean, std = arr.mean(), arr.std()
        lo, hi = mean - sigma * std, mean + sigma * std
        return [p for p in points if p.get("value") is None or lo <= p["value"] <= hi]

    def _clean_percentile(self, points: list[dict], lower: float, upper: float) -> list[dict]:
        values = [p["value"] for p in points if p.get("value") is not None]
        if len(values) < 4:
            return points
        arr = np.array(values)
        lo, hi = np.percentile(arr, lower), np.percentile(arr, upper)
        return [p for p in points if p.get("value") is None or lo <= p["value"] <= hi]

    def _clean_minmax(self, points: list[dict], min_val: float, max_val: float) -> list[dict]:
        return [p for p in points if p.get("value") is None or min_val <= p["value"] <= max_val]

    def _clean_spatial_dedup(self, points: list[dict], distance_m: float) -> list[dict]:
        deg_approx = distance_m / 111320.0
        kept: list[dict] = []
        for p in points:
            is_dup = False
            for k in kept:
                if abs(p["lat"] - k["lat"]) < deg_approx and abs(p["lon"] - k["lon"]) < deg_approx:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(p)
        return kept

    def _clean_edge_buffer(self, points: list[dict], meters: float) -> list[dict]:
        if not points:
            return points
        lats = [p["lat"] for p in points]
        lons = [p["lon"] for p in points]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        deg_buf = meters / 111320.0
        return [
            p
            for p in points
            if (
                p["lat"] > min_lat + deg_buf
                and p["lat"] < max_lat - deg_buf
                and p["lon"] > min_lon + deg_buf
                and p["lon"] < max_lon - deg_buf
            )
        ]
