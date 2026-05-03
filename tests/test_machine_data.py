"""Tests for machine data parser — yield monitor, as-applied, planting."""

import json

import pytest

from openfmis.services.machine_data import (
    MachineDataParseResult,
    filter_machine_data,
    parse_machine_data,
    summarize,
    to_numpy_arrays,
)


def _yield_csv() -> bytes:
    return (
        b"Latitude,Longitude,Yld_Vol_Dr,Moisture,Speed,Crop\n"
        b"40.1234,-96.5678,180.5,14.2,4.5,Corn\n"
        b"40.1235,-96.5679,195.3,13.8,4.6,Corn\n"
        b"40.1236,-96.5680,0.0,15.0,0.5,Corn\n"
        b"40.1237,-96.5681,210.1,14.5,4.7,Corn\n"
        b"40.1238,-96.5682,165.2,14.0,4.4,Corn\n"
    )


def _applied_csv() -> bytes:
    return (
        b"lat,lon,rate,product,speed,tgt_rate\n"
        b"40.1234,-96.5678,28.5,28-0-0,5.2,30.0\n"
        b"40.1235,-96.5679,29.1,28-0-0,5.3,30.0\n"
        b"40.1236,-96.5680,31.0,28-0-0,5.1,30.0\n"
    )


def _planting_csv() -> bytes:
    return (
        b"Latitude,Longitude,Population,Hybrid,Speed,Depth\n"
        b"40.1234,-96.5678,34000,DKC62-08,4.5,2.0\n"
        b"40.1235,-96.5679,33500,DKC62-08,4.6,1.9\n"
        b"40.1236,-96.5680,34500,DKC62-08,4.4,2.1\n"
    )


class TestParseYield:
    def test_basic_yield_csv(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        assert result.data_type == "yield"
        assert result.raw_count == 5
        assert len(result.points) == 5
        assert result.crop == "Corn"
        assert result.unit == "bu/ac"

    def test_yield_primary_value(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        assert result.primary_value_column is not None
        # Should detect Yld_Vol_Dr as dry_yield
        vals = [p.attributes.get("dry_yield") for p in result.points]
        assert 180.5 in vals

    def test_yield_moisture_parsed(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        moistures = [p.attributes.get("moisture") for p in result.points]
        assert 14.2 in moistures

    def test_yield_metadata(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        assert result.metadata["total_rows"] == 5
        assert result.metadata["valid_points"] == 5


class TestParseApplied:
    def test_basic_applied_csv(self):
        result = parse_machine_data(_applied_csv(), "applied.csv", "as_applied")
        assert result.data_type == "as_applied"
        assert len(result.points) == 3
        assert result.unit == "gal/ac"

    def test_applied_rate_parsed(self):
        result = parse_machine_data(_applied_csv(), "applied.csv", "as_applied")
        rates = [p.attributes.get("rate_actual") for p in result.points]
        assert 28.5 in rates

    def test_applied_target_rate(self):
        result = parse_machine_data(_applied_csv(), "applied.csv", "as_applied")
        targets = [p.attributes.get("rate_target") for p in result.points]
        assert 30.0 in targets


class TestParsePlanting:
    def test_basic_planting_csv(self):
        result = parse_machine_data(_planting_csv(), "planting.csv", "planting")
        assert result.data_type == "planting"
        assert len(result.points) == 3
        assert result.unit == "seeds/ac"

    def test_planting_population(self):
        result = parse_machine_data(_planting_csv(), "planting.csv", "planting")
        pops = [p.attributes.get("population") for p in result.points]
        assert 34000.0 in pops

    def test_planting_hybrid_detected(self):
        result = parse_machine_data(_planting_csv(), "planting.csv", "planting")
        assert result.crop == "DKC62-08"


class TestParseErrors:
    def test_unknown_data_type(self):
        with pytest.raises(ValueError, match="Unknown data_type"):
            parse_machine_data(b"", "test.csv", "bogus")

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_machine_data(b"", "test.xlsx", "yield")

    def test_no_header(self):
        with pytest.raises(ValueError, match="no header"):
            parse_machine_data(b"", "test.csv", "yield")

    def test_no_lat_lon(self):
        csv_data = b"foo,bar\n1,2\n"
        with pytest.raises(ValueError, match="latitude/longitude"):
            parse_machine_data(csv_data, "test.csv", "yield")

    def test_invalid_coordinates(self):
        csv_data = b"lat,lon,yield\nBAD,BAD,100\n40.1,-96.5,200\n"
        result = parse_machine_data(csv_data, "test.csv", "yield")
        assert len(result.points) == 1
        assert len(result.warnings) == 1


class TestGeoJSON:
    def test_geojson_yield(self):
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-96.5, 40.1]},
                    "properties": {"Yld_Vol_Dr": 180.5, "Moisture": 14.0},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-96.6, 40.2]},
                    "properties": {"Yld_Vol_Dr": 195.0, "Moisture": 13.5},
                },
            ],
        }
        content = json.dumps(geojson).encode()
        result = parse_machine_data(content, "yield.geojson", "yield")
        assert len(result.points) == 2
        assert result.points[0].attributes.get("dry_yield") == 180.5


class TestFilter:
    def test_filter_by_value(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        filtered = filter_machine_data(result, min_value=100, max_value=300)
        # Row with 0.0 yield should be removed
        vals = [p.attributes.get("dry_yield") for p in filtered.points]
        assert all(v is None or v >= 100 for v in vals)

    def test_filter_by_speed(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        filtered = filter_machine_data(result, min_speed=2.0)
        # Row with speed=0.5 should be removed
        speeds = [p.attributes.get("speed") for p in filtered.points]
        assert all(s is None or s >= 2.0 for s in speeds)

    def test_filter_metadata(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        filtered = filter_machine_data(result, min_value=100)
        assert "removed_by_filter" in filtered.metadata
        assert "filtered_count" in filtered.metadata

    def test_filter_preserves_crop(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        filtered = filter_machine_data(result, min_value=100)
        assert filtered.crop == "Corn"


class TestToNumpy:
    def test_to_arrays(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        points, values, times = to_numpy_arrays(result)
        assert points.shape[1] == 2
        assert values.ndim == 1
        assert len(values) > 0

    def test_values_match(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        _, values, _ = to_numpy_arrays(result)
        assert 180.5 in values


class TestSummarize:
    def test_yield_summary(self):
        result = parse_machine_data(_yield_csv(), "yield.csv", "yield")
        stats = summarize(result)
        assert stats["data_type"] == "yield"
        assert stats["total_points"] == 5
        assert stats["crop"] == "Corn"
        assert "mean" in stats
        assert "std" in stats
        assert "cv_pct" in stats

    def test_empty_summary(self):
        result = MachineDataParseResult(data_type="yield")
        stats = summarize(result)
        assert stats["total_points"] == 0
        assert "mean" not in stats
