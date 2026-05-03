"""Sampling point generation algorithms — ported from open-sample (TypeScript/Turf.js).

Five strategies for placing statistically robust sample locations within a polygon:
  - Random (Poisson-disk rejection sampling)
  - Grid (iterative cell-size convergence)
  - Clustered (K cluster centres + scatter)
  - W-pattern (transect along W-shaped path)
  - SSUS (Stratified Systematic Unaligned Sampling)

All functions accept a Shapely Polygon and return a list of (lon, lat) tuples.
Distances are in metres.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from pyproj import Geod
from shapely.geometry import Point

if TYPE_CHECKING:
    from shapely.geometry import Polygon

_geod = Geod(ellps="WGS84")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Geodesic distance in metres between two (lon, lat) points."""
    _, _, dist = _geod.inv(a[0], a[1], b[0], b[1])
    return dist


def _satisfies_min_distance(
    candidate: tuple[float, float],
    existing: list[tuple[float, float]],
    min_distance: float,
) -> bool:
    for pt in existing:
        if _distance_m(candidate, pt) < min_distance:
            return False
    return True


def _random_point_in_bbox(
    minx: float,
    miny: float,
    maxx: float,
    maxy: float,
) -> tuple[float, float]:
    lng = minx + random.random() * (maxx - minx)
    lat = miny + random.random() * (maxy - miny)
    return (lng, lat)


def _to_polygon(geom):
    """Coerce a Polygon or MultiPolygon to a single Polygon."""
    if geom.geom_type == "MultiPolygon":
        # Use the largest polygon by area
        return max(geom.geoms, key=lambda g: g.area)
    return geom


def _polygon_area_m2(polygon) -> float:
    """Approximate polygon area in square metres using the geodesic."""
    poly = _to_polygon(polygon)
    lons, lats = poly.exterior.coords.xy
    area, _ = _geod.polygon_area_perimeter(list(lons), list(lats))
    return abs(area)


def buffer_polygon(polygon: Polygon, buffer_m: float) -> Polygon:
    """Inward buffer (negative) by *buffer_m* metres (approximate)."""
    if buffer_m <= 0:
        return polygon
    # Approximate degrees per metre at polygon centroid
    cy = polygon.centroid.y
    deg_per_m_lat = 1.0 / 111_320.0
    deg_per_m_lng = 1.0 / (111_320.0 * math.cos(math.radians(cy)))
    avg_deg = (deg_per_m_lat + deg_per_m_lng) / 2.0
    buffered = polygon.buffer(-buffer_m * avg_deg)
    if buffered.is_empty:
        return polygon  # buffer too large — fall back to original
    return buffered


# ── Random ───────────────────────────────────────────────────────────────────


def generate_random(
    polygon: Polygon,
    count: int,
    min_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """Poisson-disk rejection sampling within *polygon*."""
    minx, miny, maxx, maxy = polygon.bounds
    points: list[tuple[float, float]] = []
    max_attempts = count * 200

    for _ in range(max_attempts):
        if len(points) >= count:
            break
        candidate = _random_point_in_bbox(minx, miny, maxx, maxy)
        if not polygon.contains(Point(candidate)):
            continue
        if not _satisfies_min_distance(candidate, points, min_distance):
            continue
        points.append(candidate)

    return points


# ── Grid ─────────────────────────────────────────────────────────────────────


def generate_grid(
    polygon: Polygon,
    count: int,
    min_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """Uniform grid snapped to *count* within the polygon."""
    area = _polygon_area_m2(polygon)
    cell_size_m = math.sqrt(area / max(count, 1))
    cell_size_m = max(cell_size_m, min_distance) if min_distance > 0 else cell_size_m

    minx, miny, maxx, maxy = polygon.bounds

    # Approximate degrees per metre at polygon centroid
    cy = polygon.centroid.y
    deg_per_m_lat = 1.0 / 111_320.0
    deg_per_m_lng = 1.0 / (111_320.0 * math.cos(math.radians(cy)))

    best_points: list[tuple[float, float]] = []

    for _ in range(10):
        step_lng = cell_size_m * deg_per_m_lng
        step_lat = cell_size_m * deg_per_m_lat
        if step_lng <= 0 or step_lat <= 0:
            break

        pts: list[tuple[float, float]] = []
        y = miny + step_lat / 2
        while y <= maxy:
            x = minx + step_lng / 2
            while x <= maxx:
                if polygon.contains(Point(x, y)):
                    pts.append((x, y))
                x += step_lng
            y += step_lat

        if abs(len(pts) - count) <= max(1, count * 0.1):
            best_points = pts[:count]
            break

        if len(pts) > count:
            cell_size_m *= 1.1
        else:
            cell_size_m *= 0.9

        best_points = pts[:count]

    return best_points


# ── Clustered ────────────────────────────────────────────────────────────────


def _random_point_in_circle(
    centre: tuple[float, float],
    radius_m: float,
) -> tuple[float, float]:
    r = radius_m * math.sqrt(random.random())
    theta = random.random() * 2 * math.pi
    d_lat = (r * math.cos(theta)) / 111_320.0
    d_lng = (r * math.sin(theta)) / (111_320.0 * math.cos(math.radians(centre[1])))
    return (centre[0] + d_lng, centre[1] + d_lat)


def generate_clustered(
    polygon: Polygon,
    count: int,
    min_distance: float = 0.0,
    cluster_count: int = 3,
    min_cluster_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """K cluster centres via random placement, then scatter points around each."""
    k = max(2, cluster_count)
    centre_min_dist = min_cluster_distance if min_cluster_distance > 0 else min_distance * 3
    centres = generate_random(polygon, k, centre_min_dist)
    if not centres:
        return []

    cluster_radius = max(min_distance * 3, 100.0)
    points_per_cluster = math.ceil(count / len(centres))
    points: list[tuple[float, float]] = []

    for centre in centres:
        added = 0
        for _ in range(200):
            if added >= points_per_cluster or len(points) >= count:
                break
            candidate = _random_point_in_circle(centre, cluster_radius)
            if not polygon.contains(Point(candidate)):
                continue
            if not _satisfies_min_distance(candidate, points, min_distance):
                continue
            points.append(candidate)
            added += 1

    return points[:count]


# ── W-Pattern ────────────────────────────────────────────────────────────────


def _interpolate_line(vertices: list[tuple[float, float]], frac: float) -> tuple[float, float]:
    """Return the point at *frac* (0..1) along a polyline defined by *vertices*."""
    # Compute cumulative segment lengths
    lengths: list[float] = [0.0]
    for i in range(1, len(vertices)):
        lengths.append(lengths[-1] + _distance_m(vertices[i - 1], vertices[i]))
    total = lengths[-1]
    if total == 0:
        return vertices[0]
    target = frac * total
    for i in range(1, len(lengths)):
        if lengths[i] >= target:
            seg_len = lengths[i] - lengths[i - 1]
            if seg_len == 0:
                return vertices[i]
            t = (target - lengths[i - 1]) / seg_len
            x = vertices[i - 1][0] + t * (vertices[i][0] - vertices[i - 1][0])
            y = vertices[i - 1][1] + t * (vertices[i][1] - vertices[i - 1][1])
            return (x, y)
    return vertices[-1]


def generate_w(
    polygon: Polygon,
    count: int,
    min_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """W-shaped transect across the polygon bounding box, clipped to polygon."""
    minx, miny, maxx, maxy = polygon.bounds
    inset_x = (maxx - minx) * 0.05
    inset_y = (maxy - miny) * 0.05
    left, right = minx + inset_x, maxx - inset_x
    top, bottom = maxy - inset_y, miny + inset_y
    mid_x = (left + right) / 2
    quarter_x = (left + mid_x) / 2
    three_quarter_x = (mid_x + right) / 2

    w_vertices: list[tuple[float, float]] = [
        (left, top),
        (quarter_x, bottom),
        (mid_x, top),
        (three_quarter_x, bottom),
        (right, top),
    ]

    # Oversample along the W path
    oversample = max(count * 3, 50)
    candidates: list[tuple[float, float]] = []
    for i in range(oversample):
        frac = i / max(oversample - 1, 1)
        candidates.append(_interpolate_line(w_vertices, frac))

    # Keep only points inside polygon
    inside = [pt for pt in candidates if polygon.contains(Point(pt))]

    # Select evenly spaced subset
    points: list[tuple[float, float]] = []
    if len(inside) <= count:
        for pt in inside:
            if _satisfies_min_distance(pt, points, min_distance):
                points.append(pt)
    else:
        for i in range(count):
            idx = round(i / max(count - 1, 1) * (len(inside) - 1))
            pt = inside[idx]
            if _satisfies_min_distance(pt, points, min_distance):
                points.append(pt)

        # Fill remaining from unused candidates
        if len(points) < count:
            for pt in inside:
                if len(points) >= count:
                    break
                if _satisfies_min_distance(pt, points, min_distance):
                    points.append(pt)

    return points


# ── SSUS (Stratified Systematic Unaligned Sampling) ─────────────────────────


def generate_ssus(
    polygon: Polygon,
    count: int,
    min_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """Stratified Systematic Unaligned Sampling.

    Divides the polygon's bounding box into a grid of cells (oversampled
    to account for polygon coverage). Each row gets a shared random
    x-offset and each column gets a shared random y-offset.  One point
    is placed per cell using those offsets, keeping only points inside
    the polygon.  This gives better spatial coverage than pure random
    while avoiding the rigidity of a uniform grid.
    """
    if count <= 0:
        return []

    minx, miny, maxx, maxy = polygon.bounds
    width_m = _distance_m((minx, miny), (maxx, miny))
    height_m = _distance_m((minx, miny), (minx, maxy))
    if width_m == 0 or height_m == 0:
        return []

    # Oversample: polygon may cover only a fraction of its bbox
    bbox_area = width_m * height_m
    poly_area = _polygon_area_m2(polygon)
    coverage = max(0.1, min(1.0, poly_area / bbox_area))
    target_cells = math.ceil(count / coverage)

    aspect = width_m / height_m
    cols = max(1, round(math.sqrt(target_cells * aspect)))
    rows = max(1, round(target_cells / cols))

    cell_w = (maxx - minx) / cols
    cell_h = (maxy - miny) / rows

    # Per-row x-offsets, per-column y-offsets (the "unaligned" part)
    x_offsets = [random.random() * cell_w for _ in range(rows)]
    y_offsets = [random.random() * cell_h for _ in range(cols)]

    points: list[tuple[float, float]] = []
    for i in range(rows):
        for j in range(cols):
            candidate = (
                minx + j * cell_w + x_offsets[i],
                miny + i * cell_h + y_offsets[j],
            )
            if polygon.contains(Point(candidate)):
                points.append(candidate)
                if len(points) >= count:
                    return points

    return points


# ── Dispatcher ───────────────────────────────────────────────────────────────

ALGORITHMS = {
    "random": generate_random,
    "grid": generate_grid,
    "clustered": generate_clustered,
    "w": generate_w,
    "ssus": generate_ssus,
}


def generate_points(
    polygon: Polygon,
    algorithm: str,
    count: int,
    min_distance: float = 0.0,
    buffer_distance: float = 0.0,
    cluster_count: int = 3,
    min_cluster_distance: float = 0.0,
) -> list[tuple[float, float]]:
    """High-level dispatcher — applies buffer then delegates to the chosen algorithm."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm: {algorithm!r}. Choose from {list(ALGORITHMS)}")

    effective = buffer_polygon(polygon, buffer_distance) if buffer_distance > 0 else polygon

    if algorithm == "clustered":
        return generate_clustered(
            effective,
            count,
            min_distance,
            cluster_count,
            min_cluster_distance,
        )
    return ALGORITHMS[algorithm](effective, count, min_distance)
