"""Machine data parsers — yield monitor, as-applied, planting.

Parses structured field operation data from CSV, shapefiles, and
GeoJSON into standardized records ready for PointDataset ingestion
and FieldEvent creation.  Handles the common column-naming
conventions from John Deere, Case IH, AGCO, and generic AgLeader
exports.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import fiona
import numpy as np
from shapely.geometry import shape

log = logging.getLogger(__name__)


# ── Column name mappings per vendor/format ──────────────────────────────


_YIELD_COLUMNS = {
    "yld_vol_dr": "dry_yield",
    "yld_mass_d": "dry_yield",
    "dry_yield": "dry_yield",
    "yield": "dry_yield",
    "bu_ac": "dry_yield",
    "bu/ac": "dry_yield",
    "yld_vol_we": "wet_yield",
    "wet_yield": "wet_yield",
    "moisture": "moisture",
    "grain_mois": "moisture",
    "crop_moist": "moisture",
    "swth_wdth_": "swath_width",
    "swath_wdth": "swath_width",
    "swath_width": "swath_width",
    "pass_num": "pass_num",
    "distance": "distance",
    "speed": "speed",
    "heading": "heading",
    "crop": "crop",
    "product": "crop",
    "variety": "hybrid",
    "hybrid": "hybrid",
    "elevation": "elevation",
}

_APPLIED_COLUMNS = {
    "rt_apd_ct_": "rate_actual",
    "rt_apd_ms_": "rate_actual",
    "rate": "rate_actual",
    "rate_actual": "rate_actual",
    "applied_rate": "rate_actual",
    "app_rate": "rate_actual",
    "product_ra": "rate_actual",
    "tgt_rate": "rate_target",
    "target_rat": "rate_target",
    "target_rate": "rate_target",
    "product": "product",
    "product_na": "product",
    "speed": "speed",
    "swth_wdth_": "swath_width",
    "swath_width": "swath_width",
    "distance": "distance",
    "heading": "heading",
    "elevation": "elevation",
}

_PLANTING_COLUMNS = {
    "rt_apd_ct_": "population",
    "population": "population",
    "pop_actual": "population",
    "seed_rate": "population",
    "tgt_rate": "target_pop",
    "target_pop": "target_pop",
    "target_rat": "target_pop",
    "variety": "hybrid",
    "hybrid": "hybrid",
    "product": "hybrid",
    "speed": "speed",
    "swth_wdth_": "row_spacing",
    "swath_width": "row_spacing",
    "row_spacin": "row_spacing",
    "spacing": "row_spacing",
    "distance": "distance",
    "heading": "heading",
    "depth": "depth",
    "singulatio": "singulation",
    "singulation": "singulation",
    "downforce": "downforce",
    "elevation": "elevation",
    "crop": "crop",
}

_LAT_PATTERNS = {"latitude", "lat", "y", "ylat", "point_y", "lat_dd"}
_LON_PATTERNS = {"longitude", "lon", "long", "x", "xlong", "xlon", "point_x", "lon_dd"}


@dataclass
class MachineDataPoint:
    """A single machine data observation."""

    lat: float
    lon: float
    timestamp: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class MachineDataParseResult:
    """Result of parsing a machine data file."""

    data_type: str  # "yield", "as_applied", "planting"
    points: list[MachineDataPoint] = field(default_factory=list)
    raw_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    primary_value_column: str | None = None
    unit: str | None = None
    crop: str | None = None


def parse_machine_data(
    file_content: bytes,
    filename: str,
    data_type: str,
) -> MachineDataParseResult:
    """Parse a machine data file into standardized records.

    Args:
        file_content: Raw file bytes.
        filename: Original filename (used for format detection).
        data_type: One of "yield", "as_applied", "planting".

    Returns:
        MachineDataParseResult with parsed points and metadata.
    """
    if data_type not in ("yield", "as_applied", "planting"):
        raise ValueError(f"Unknown data_type: {data_type}")

    ext = os.path.splitext(filename.lower())[1]

    if ext == ".csv":
        return _parse_csv(file_content, data_type)
    elif ext in (".geojson", ".json"):
        return _parse_geospatial(file_content, filename, data_type)
    elif ext == ".zip":
        return _parse_shapefile_zip(file_content, data_type)
    else:
        raise ValueError(f"Unsupported file type: {ext}")


def _get_column_mapping(data_type: str) -> dict[str, str]:
    if data_type == "yield":
        return _YIELD_COLUMNS
    elif data_type == "as_applied":
        return _APPLIED_COLUMNS
    elif data_type == "planting":
        return _PLANTING_COLUMNS
    return {}


def _map_columns(raw_columns: list[str], data_type: str) -> dict[str, str]:
    """Map raw column names to standardized names.

    Returns dict of {raw_column: standardized_name}.
    """
    mapping = _get_column_mapping(data_type)
    result: dict[str, str] = {}
    for col in raw_columns:
        key = col.lower().strip()
        if key in mapping:
            result[col] = mapping[key]
    return result


def _detect_primary_value(mapped: dict[str, str], data_type: str) -> str | None:
    """Detect the primary value column based on data type."""
    targets = {
        "yield": "dry_yield",
        "as_applied": "rate_actual",
        "planting": "population",
    }
    target = targets.get(data_type)
    if not target:
        return None
    for raw, std in mapped.items():
        if std == target:
            return raw
    return None


def _detect_unit(mapped: dict[str, str], data_type: str) -> str | None:
    """Guess unit based on data type."""
    units = {
        "yield": "bu/ac",
        "as_applied": "gal/ac",
        "planting": "seeds/ac",
    }
    return units.get(data_type)


def _detect_crop(row: dict[str, Any], mapped: dict[str, str]) -> str | None:
    """Try to extract crop name from a row."""
    for raw, std in mapped.items():
        if std in ("crop", "hybrid") and raw in row:
            val = row[raw]
            if val and str(val).strip():
                return str(val).strip()
    return None


def _parse_timestamp(row: dict[str, Any]) -> datetime | None:
    """Try to extract timestamp from common time columns."""
    for key in ("timestamp", "time", "datetime", "date", "gps_time", "isotime"):
        for col in row:
            if col.lower().strip() == key and row[col]:
                try:
                    return datetime.fromisoformat(str(row[col]))
                except (ValueError, TypeError):
                    pass
    return None


# ── CSV parser ──────────────────────────────────────────────────────────


def _parse_csv(content: bytes, data_type: str) -> MachineDataParseResult:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")

    all_columns = list(reader.fieldnames)
    cols_lower = {c.lower().strip(): c for c in all_columns}

    # Find lat/lon columns
    lat_col = None
    lon_col = None
    for pat in _LAT_PATTERNS:
        if pat in cols_lower:
            lat_col = cols_lower[pat]
            break
    for pat in _LON_PATTERNS:
        if pat in cols_lower:
            lon_col = cols_lower[pat]
            break

    if not lat_col or not lon_col:
        raise ValueError(f"Cannot find latitude/longitude columns in CSV. Available: {all_columns}")

    mapped = _map_columns(all_columns, data_type)
    primary_col = _detect_primary_value(mapped, data_type)

    result = MachineDataParseResult(
        data_type=data_type,
        primary_value_column=primary_col,
        unit=_detect_unit(mapped, data_type),
    )

    for row in reader:
        result.raw_count += 1
        try:
            lat = float(row[lat_col])
            lon = float(row[lon_col])
        except (ValueError, TypeError, KeyError):
            result.warnings.append(f"Row {result.raw_count}: invalid coordinates")
            continue

        if lat == 0 and lon == 0:
            continue

        attrs: dict[str, Any] = {}
        for raw_col, std_name in mapped.items():
            if raw_col in row and row[raw_col]:
                val = row[raw_col]
                try:
                    attrs[std_name] = float(val)
                except (ValueError, TypeError):
                    attrs[std_name] = str(val)

        ts = _parse_timestamp(row)

        if result.crop is None:
            result.crop = _detect_crop(row, mapped)

        result.points.append(MachineDataPoint(lat=lat, lon=lon, timestamp=ts, attributes=attrs))

    result.metadata = {
        "columns_detected": list(mapped.values()),
        "primary_value_column": primary_col,
        "total_rows": result.raw_count,
        "valid_points": len(result.points),
    }

    return result


# ── Shapefile / GeoJSON parser ──────────────────────────────────────────


def _parse_geospatial(
    content: bytes,
    filename: str,
    data_type: str,
) -> MachineDataParseResult:
    with fiona.MemoryFile(content) as memfile:
        with memfile.open() as src:
            return _parse_fiona_source(src, data_type)


def _parse_shapefile_zip(
    content: bytes,
    data_type: str,
) -> MachineDataParseResult:
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
            return _parse_fiona_source(src, data_type)


def _parse_fiona_source(
    src: fiona.Collection,
    data_type: str,
) -> MachineDataParseResult:
    props = list(src.schema.get("properties", {}).keys())
    mapped = _map_columns(props, data_type)
    primary_col = _detect_primary_value(mapped, data_type)

    result = MachineDataParseResult(
        data_type=data_type,
        primary_value_column=primary_col,
        unit=_detect_unit(mapped, data_type),
    )

    for feat in src:
        result.raw_count += 1
        if not feat.geometry:
            continue

        geom = shape(feat.geometry)
        centroid = geom.centroid
        lat, lon = centroid.y, centroid.x

        if lat == 0 and lon == 0:
            continue

        attrs: dict[str, Any] = {}
        row = dict(feat.properties or {})
        for raw_col, std_name in mapped.items():
            if raw_col in row and row[raw_col] is not None:
                val = row[raw_col]
                try:
                    attrs[std_name] = float(val)
                except (ValueError, TypeError):
                    attrs[std_name] = str(val)

        if result.crop is None:
            result.crop = _detect_crop(row, mapped)

        result.points.append(MachineDataPoint(lat=lat, lon=lon, attributes=attrs))

    result.metadata = {
        "columns_detected": list(mapped.values()),
        "primary_value_column": primary_col,
        "total_rows": result.raw_count,
        "valid_points": len(result.points),
        "crs": str(src.crs_wkt or ""),
    }

    return result


# ── Cleaning / filtering ───────────────────────────────────────────────


def filter_machine_data(
    result: MachineDataParseResult,
    min_value: float | None = None,
    max_value: float | None = None,
    min_speed: float | None = None,
    max_speed: float | None = None,
    min_moisture: float | None = None,
    max_moisture: float | None = None,
) -> MachineDataParseResult:
    """Filter machine data points by value and operational thresholds.

    Common cleaning rules for yield monitors, as-applied, and planting:
    - Remove extreme values (e.g. yield < 0 or > 500 bu/ac)
    - Remove low-speed points (headland turns)
    - Remove extreme moisture readings

    Returns a new result with filtered points and updated metadata.
    """
    primary = {
        "yield": "dry_yield",
        "as_applied": "rate_actual",
        "planting": "population",
    }.get(result.data_type)

    filtered: list[MachineDataPoint] = []
    removed = 0

    for pt in result.points:
        keep = True

        if primary and min_value is not None:
            val = pt.attributes.get(primary)
            if isinstance(val, (int, float)) and val < min_value:
                keep = False

        if primary and max_value is not None:
            val = pt.attributes.get(primary)
            if isinstance(val, (int, float)) and val > max_value:
                keep = False

        if min_speed is not None:
            spd = pt.attributes.get("speed")
            if isinstance(spd, (int, float)) and spd < min_speed:
                keep = False

        if max_speed is not None:
            spd = pt.attributes.get("speed")
            if isinstance(spd, (int, float)) and spd > max_speed:
                keep = False

        if min_moisture is not None:
            moist = pt.attributes.get("moisture")
            if isinstance(moist, (int, float)) and moist < min_moisture:
                keep = False

        if max_moisture is not None:
            moist = pt.attributes.get("moisture")
            if isinstance(moist, (int, float)) and moist > max_moisture:
                keep = False

        if keep:
            filtered.append(pt)
        else:
            removed += 1

    new_result = MachineDataParseResult(
        data_type=result.data_type,
        points=filtered,
        raw_count=result.raw_count,
        metadata={
            **result.metadata,
            "filtered_count": len(filtered),
            "removed_by_filter": removed,
        },
        warnings=list(result.warnings),
        primary_value_column=result.primary_value_column,
        unit=result.unit,
        crop=result.crop,
    )
    return new_result


def to_numpy_arrays(
    result: MachineDataParseResult,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert parsed machine data to numpy arrays for interpolation.

    Returns:
        (points, values, timestamps) where:
        - points is (N, 2) array of (lon, lat)
        - values is (N,) array of primary values
        - timestamps is (N,) array of Unix timestamps (NaN if missing)
    """
    primary = {
        "yield": "dry_yield",
        "as_applied": "rate_actual",
        "planting": "population",
    }.get(result.data_type, "")

    coords = []
    vals = []
    times = []

    for pt in result.points:
        val = pt.attributes.get(primary)
        if not isinstance(val, (int, float)):
            continue
        coords.append([pt.lon, pt.lat])
        vals.append(float(val))
        if pt.timestamp:
            times.append(pt.timestamp.timestamp())
        else:
            times.append(float("nan"))

    points_arr = np.array(coords, dtype=np.float64)
    values_arr = np.array(vals, dtype=np.float64)
    times_arr = np.array(times, dtype=np.float64)

    return points_arr, values_arr, times_arr


def summarize(result: MachineDataParseResult) -> dict[str, Any]:
    """Generate summary statistics from parsed machine data."""
    primary = {
        "yield": "dry_yield",
        "as_applied": "rate_actual",
        "planting": "population",
    }.get(result.data_type, "")

    vals = [
        pt.attributes[primary]
        for pt in result.points
        if primary in pt.attributes and isinstance(pt.attributes[primary], (int, float))
    ]

    stats: dict[str, Any] = {
        "data_type": result.data_type,
        "total_points": len(result.points),
        "crop": result.crop,
        "unit": result.unit,
    }

    if vals:
        arr = np.array(vals)
        stats.update(
            {
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
                "median": float(np.median(arr)),
                "cv_pct": float(np.std(arr) / np.mean(arr) * 100) if np.mean(arr) != 0 else 0,
            }
        )

    return stats
