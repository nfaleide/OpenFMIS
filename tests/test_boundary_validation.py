"""Tests for boundary validation service."""

from shapely.geometry import Polygon
from shapely.geometry import mapping as shapely_mapping

from openfmis.services.boundary_validation import (
    BoundaryValidationResult,
    validate_boundary,
)


def _rect(lon, lat, dlon, dlat):
    """Create a simple rectangular polygon GeoJSON at the given location."""
    return shapely_mapping(
        Polygon(
            [
                (lon, lat),
                (lon + dlon, lat),
                (lon + dlon, lat + dlat),
                (lon, lat + dlat),
                (lon, lat),
            ]
        )
    )


# --- Valid geometry ---


class TestValidBoundary:
    def test_valid_polygon(self):
        """Normal-sized field polygon passes validation."""
        # ~160 acres at 40°N (approx 0.01 deg lat x 0.01 deg lon)
        geojson = _rect(-96.0, 40.0, 0.05, 0.05)
        result = validate_boundary(geojson)
        assert result.valid
        assert result.area_acres is not None
        assert result.area_acres > 0
        assert len(result.errors) == 0

    def test_multipolygon(self):
        """MultiPolygon is accepted."""
        from shapely.geometry import MultiPolygon

        p1 = Polygon([(-96, 40), (-95.99, 40), (-95.99, 40.01), (-96, 40.01), (-96, 40)])
        p2 = Polygon([(-95, 40), (-94.99, 40), (-94.99, 40.01), (-95, 40.01), (-95, 40)])
        mp = MultiPolygon([p1, p2])
        geojson = shapely_mapping(mp)
        result = validate_boundary(geojson)
        assert result.valid
        assert result.area_acres is not None


# --- Geometry type errors ---


class TestGeometryType:
    def test_point_rejected(self):
        geojson = {"type": "Point", "coordinates": [-96, 40]}
        result = validate_boundary(geojson)
        assert not result.valid
        assert any(i.code == "WRONG_TYPE" for i in result.issues)

    def test_linestring_rejected(self):
        geojson = {"type": "LineString", "coordinates": [[-96, 40], [-95, 41]]}
        result = validate_boundary(geojson)
        assert not result.valid
        assert any(i.code == "WRONG_TYPE" for i in result.issues)

    def test_invalid_geojson(self):
        result = validate_boundary({"type": "Bogus"})
        assert not result.valid
        assert any(i.code == "INVALID_GEOJSON" for i in result.issues)


# --- Empty geometry ---


class TestEmpty:
    def test_empty_polygon(self):
        geojson = shapely_mapping(Polygon())
        result = validate_boundary(geojson)
        assert not result.valid
        assert any(i.code == "EMPTY_GEOMETRY" for i in result.issues)


# --- Coordinate range ---


class TestCoordinateRange:
    def test_latitude_out_of_range(self):
        geojson = _rect(-96, 91, 0.01, 0.01)
        result = validate_boundary(geojson)
        assert not result.valid
        assert any(i.code == "LAT_OUT_OF_RANGE" for i in result.issues)

    def test_longitude_out_of_range_warning(self):
        geojson = _rect(179.99, 40, 0.05, 0.05)
        result = validate_boundary(geojson)
        # Longitude out of range is a warning, not error
        assert any(i.code == "LON_OUT_OF_RANGE" for i in result.issues)
        lon_issue = [i for i in result.issues if i.code == "LON_OUT_OF_RANGE"][0]
        assert lon_issue.severity == "warning"


# --- Area bounds ---


class TestAreaBounds:
    def test_area_too_small(self):
        # Tiny polygon — well under 0.5 acres
        geojson = _rect(-96, 40, 0.0001, 0.0001)
        result = validate_boundary(geojson)
        assert any(i.code == "AREA_TOO_SMALL" for i in result.issues)

    def test_area_too_large(self):
        # Huge polygon — well over 5000 acres
        geojson = _rect(-96, 40, 2.0, 2.0)
        result = validate_boundary(geojson)
        assert any(i.code == "AREA_TOO_LARGE" for i in result.issues)

    def test_custom_area_bounds(self):
        geojson = _rect(-96, 40, 0.05, 0.05)
        # Set very restrictive bounds
        result = validate_boundary(geojson, min_area_acres=99999)
        assert any(i.code == "AREA_TOO_SMALL" for i in result.issues)


# --- Self-intersection ---


class TestSelfIntersection:
    def test_self_intersecting_repaired(self):
        """Bowtie polygon is auto-repaired."""
        bowtie = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-96, 40],
                    [-95, 41],
                    [-95, 40],
                    [-96, 41],
                    [-96, 40],
                ]
            ],
        }
        result = validate_boundary(bowtie, auto_repair=True)
        assert result.valid
        assert result.repaired_geojson is not None
        assert any(i.code == "SELF_INTERSECTION_REPAIRED" for i in result.issues)

    def test_self_intersecting_no_repair(self):
        """Without auto_repair, self-intersection is an error."""
        bowtie = {
            "type": "Polygon",
            "coordinates": [
                [
                    [-96, 40],
                    [-95, 41],
                    [-95, 40],
                    [-96, 41],
                    [-96, 40],
                ]
            ],
        }
        result = validate_boundary(bowtie, auto_repair=False)
        assert not result.valid
        assert any(i.code == "SELF_INTERSECTION" for i in result.issues)


# --- Result properties ---


class TestResultProperties:
    def test_errors_and_warnings(self):
        result = BoundaryValidationResult(valid=False)
        from openfmis.services.boundary_validation import BoundaryIssue

        result.issues.append(BoundaryIssue("error", "E1", "err"))
        result.issues.append(BoundaryIssue("warning", "W1", "warn"))
        result.issues.append(BoundaryIssue("error", "E2", "err2"))
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_area_returned(self):
        geojson = _rect(-96, 40, 0.05, 0.05)
        result = validate_boundary(geojson, max_area_acres=999999)
        assert result.area_acres is not None
        # 0.05 deg x 0.05 deg at 40N ≈ 5862 acres
        assert 4000 < result.area_acres < 8000
