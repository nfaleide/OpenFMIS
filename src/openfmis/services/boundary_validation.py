"""Field boundary geometry validation.

Validates polygon geometries before they're stored as field boundaries.
Checks for self-intersections, area bounds, hole validity, and
coordinate system sanity.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.validation import explain_validity, make_valid

log = logging.getLogger(__name__)

# Area bounds in acres (1 acre = 4046.8564224 m²)
ACRES_TO_SQ_M = 4046.8564224
MIN_AREA_ACRES = 0.5
MAX_AREA_ACRES = 5000.0

# Approximate conversion: 1 degree lat ≈ 111,320 m, 1 degree lon varies
# At 40°N: 1 degree lon ≈ 85,394 m
# We use a simple approximation for area in WGS84 coordinates.
DEG_LAT_TO_M = 111_320.0
DEG_LON_TO_M_AT_40N = 85_394.0  # Approximate for Corn Belt latitudes


@dataclass
class BoundaryIssue:
    """A validation issue with a field boundary."""

    severity: str  # "error" or "warning"
    code: str
    message: str


@dataclass
class BoundaryValidationResult:
    """Result of boundary validation."""

    valid: bool
    issues: list[BoundaryIssue] = field(default_factory=list)
    repaired_geojson: dict[str, Any] | None = None
    area_acres: float | None = None

    @property
    def errors(self) -> list[BoundaryIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[BoundaryIssue]:
        return [i for i in self.issues if i.severity == "warning"]


def validate_boundary(
    geojson: dict[str, Any],
    min_area_acres: float = MIN_AREA_ACRES,
    max_area_acres: float = MAX_AREA_ACRES,
    auto_repair: bool = True,
) -> BoundaryValidationResult:
    """Validate a field boundary geometry.

    Checks:
    1. Valid GeoJSON geometry (Polygon or MultiPolygon)
    2. No self-intersections (optionally auto-repaired)
    3. Area within bounds (0.5–5,000 acres by default)
    4. No empty geometry
    5. Coordinates in valid WGS84 range

    Args:
        geojson: GeoJSON geometry dict.
        min_area_acres: Minimum area in acres.
        max_area_acres: Maximum area in acres.
        auto_repair: If True, attempt to fix self-intersections.

    Returns:
        BoundaryValidationResult with issues and optional repaired geometry.
    """
    result = BoundaryValidationResult(valid=True)

    # Parse geometry
    try:
        geom = shapely_shape(geojson)
    except Exception as exc:
        result.valid = False
        result.issues.append(
            BoundaryIssue("error", "INVALID_GEOJSON", f"Cannot parse geometry: {exc}")
        )
        return result

    # Check geometry type
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        result.valid = False
        result.issues.append(
            BoundaryIssue(
                "error",
                "WRONG_TYPE",
                f"Expected Polygon or MultiPolygon, got {geom.geom_type}",
            )
        )
        return result

    # Check empty
    if geom.is_empty:
        result.valid = False
        result.issues.append(BoundaryIssue("error", "EMPTY_GEOMETRY", "Geometry is empty"))
        return result

    # Check coordinate ranges (WGS84)
    bounds = geom.bounds  # (minx, miny, maxx, maxy) = (minlon, minlat, maxlon, maxlat)
    if bounds[0] < -180 or bounds[2] > 180:
        result.issues.append(
            BoundaryIssue(
                "warning",
                "LON_OUT_OF_RANGE",
                f"Longitude out of range: [{bounds[0]:.4f}, {bounds[2]:.4f}]",
            )
        )
    if bounds[1] < -90 or bounds[3] > 90:
        result.valid = False
        result.issues.append(
            BoundaryIssue(
                "error",
                "LAT_OUT_OF_RANGE",
                f"Latitude out of range: [{bounds[1]:.4f}, {bounds[3]:.4f}]",
            )
        )
        return result

    # Check self-intersection
    if not geom.is_valid:
        explanation = explain_validity(geom)
        if auto_repair:
            repaired = make_valid(geom)
            if repaired.is_valid and not repaired.is_empty:
                # Ensure MultiPolygon
                if repaired.geom_type == "Polygon":
                    repaired = MultiPolygon([repaired])
                elif repaired.geom_type == "GeometryCollection":
                    polys = [
                        g for g in repaired.geoms if g.geom_type in ("Polygon", "MultiPolygon")
                    ]
                    if not polys:
                        result.valid = False
                        result.issues.append(
                            BoundaryIssue("error", "REPAIR_FAILED", "Repair produced no polygons")
                        )
                        return result
                    repaired = MultiPolygon(
                        [
                            p
                            for g in polys
                            for p in (g.geoms if g.geom_type == "MultiPolygon" else [g])
                        ]
                    )

                result.repaired_geojson = shapely_mapping(repaired)
                result.issues.append(
                    BoundaryIssue(
                        "warning",
                        "SELF_INTERSECTION_REPAIRED",
                        f"Self-intersection repaired: {explanation}",
                    )
                )
                geom = repaired
            else:
                result.valid = False
                result.issues.append(
                    BoundaryIssue(
                        "error",
                        "SELF_INTERSECTION",
                        f"Self-intersecting geometry could not be repaired: {explanation}",
                    )
                )
                return result
        else:
            result.valid = False
            result.issues.append(
                BoundaryIssue(
                    "error",
                    "SELF_INTERSECTION",
                    f"Self-intersecting geometry: {explanation}",
                )
            )
            return result

    # Estimate area in acres
    # Use a simple approximation based on centroid latitude
    centroid = geom.centroid
    lat_rad = abs(centroid.y) * math.pi / 180
    cos_lat = max(0.01, abs(math.cos(lat_rad)))
    deg_lon_to_m = DEG_LAT_TO_M * cos_lat

    # Compute area in approximate square meters
    # For each polygon, compute area using the coordinate-based approach
    area_sq_m = _approx_area_sq_m(geom, DEG_LAT_TO_M, deg_lon_to_m)
    area_acres = area_sq_m / ACRES_TO_SQ_M
    result.area_acres = round(area_acres, 2)

    if area_acres < min_area_acres:
        result.issues.append(
            BoundaryIssue(
                "warning",
                "AREA_TOO_SMALL",
                f"Area {area_acres:.2f} acres is below minimum {min_area_acres} acres",
            )
        )

    if area_acres > max_area_acres:
        result.issues.append(
            BoundaryIssue(
                "warning",
                "AREA_TOO_LARGE",
                f"Area {area_acres:.2f} acres exceeds maximum {max_area_acres} acres",
            )
        )

    return result


def _approx_area_sq_m(
    geom: Polygon | MultiPolygon,
    deg_lat_to_m: float,
    deg_lon_to_m: float,
) -> float:
    """Approximate area in square meters from WGS84 coordinates.

    Scales the shapely area (in square degrees) by the approximate
    meters-per-degree at the geometry's centroid latitude.
    """
    # shapely .area for geographic coords gives square degrees
    area_sq_deg = geom.area
    return area_sq_deg * deg_lat_to_m * deg_lon_to_m
