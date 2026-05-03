"""Tests for reporting & analytics engine."""

import csv
import io

from openfmis.services.reports import (
    NutrientTrendPoint,
    as_applied_comparison,
    nutrient_trends,
    prescription_cost,
    prescription_cost_to_csv,
    soil_test_summary,
    soil_test_to_csv,
    yield_analysis,
    yield_analysis_to_csv,
)


class TestSoilTestSummary:
    def test_basic_summary(self):
        data = [
            {"p_ppm": 15, "k_ppm": 150, "ph": 6.5, "om_pct": 3.2},
            {"p_ppm": 20, "k_ppm": 180, "ph": 6.8, "om_pct": 2.8},
            {"p_ppm": 12, "k_ppm": 120, "ph": 6.2, "om_pct": 3.5},
        ]
        result = soil_test_summary("North 40", 2024, data)
        assert result.field_name == "North 40"
        assert result.crop_year == 2024
        assert result.samples == 3
        assert "p_ppm" in result.analytes
        assert result.analytes["p_ppm"]["min"] == 12.0
        assert result.analytes["p_ppm"]["max"] == 20.0
        assert result.analytes["p_ppm"]["n"] == 3

    def test_empty_data(self):
        result = soil_test_summary("Field", 2024, [])
        assert result.samples == 0
        assert result.analytes == {}

    def test_mixed_analytes(self):
        data = [
            {"p_ppm": 15, "k_ppm": 150},
            {"p_ppm": 20},  # Missing k_ppm
        ]
        result = soil_test_summary("Field", 2024, data)
        assert result.analytes["p_ppm"]["n"] == 2
        assert result.analytes["k_ppm"]["n"] == 1

    def test_unit_detection(self):
        data = [{"p_ppm": 15, "ph": 6.5}]
        result = soil_test_summary("Field", 2024, data)
        assert result.analytes["p_ppm"]["unit"] == "ppm"
        assert result.analytes["ph"]["unit"] == ""


class TestYieldAnalysis:
    def test_basic_yield(self):
        points = [
            {"yield": 180, "hybrid": "DKC62-08"},
            {"yield": 195, "hybrid": "DKC62-08"},
            {"yield": 170, "hybrid": "P1197"},
            {"yield": 200, "hybrid": "P1197"},
        ]
        result = yield_analysis("North 40", 2024, points, crop="Corn")
        assert result.field_name == "North 40"
        assert result.crop == "Corn"
        assert result.overall_mean > 0
        assert "hybrid" in result.by_category
        assert len(result.by_category["hybrid"]) == 2

    def test_empty_points(self):
        result = yield_analysis("Field", 2024, [])
        assert result.overall_mean == 0.0

    def test_multiple_groupings(self):
        points = [
            {"yield": 180, "hybrid": "A", "tillage": "no-till"},
            {"yield": 195, "hybrid": "B", "tillage": "no-till"},
            {"yield": 170, "hybrid": "A", "tillage": "strip-till"},
        ]
        result = yield_analysis("Field", 2024, points, group_by=["hybrid", "tillage"])
        assert "hybrid" in result.by_category
        assert "tillage" in result.by_category


class TestNutrientTrends:
    def test_basic_trend(self):
        data = [
            (2020, [15, 18, 12]),
            (2021, [20, 22]),
            (2022, [17, 19, 21]),
        ]
        points = nutrient_trends("p_ppm", "ppm", data)
        assert len(points) == 3
        assert all(isinstance(p, NutrientTrendPoint) for p in points)
        assert points[0].year == 2020
        assert points[0].unit == "ppm"

    def test_empty_years(self):
        data = [(2020, []), (2021, [15])]
        points = nutrient_trends("p_ppm", "ppm", data)
        assert len(points) == 1  # Only 2021 has data


class TestPrescriptionCost:
    def test_basic_cost(self):
        zones = [
            {"label": "Low", "acres": 40, "rate": 120},
            {"label": "Medium", "acres": 80, "rate": 160},
            {"label": "High", "acres": 40, "rate": 200},
        ]
        result = prescription_cost("N Rx 2024", "Urea", "lbs", 0.35, zones)
        assert result.rx_name == "N Rx 2024"
        assert result.total_acres == 160.0
        assert result.min_rate == 120.0
        assert result.max_rate == 200.0
        assert result.total_cost > 0
        assert len(result.zones) == 3

    def test_single_zone(self):
        result = prescription_cost(
            "Rx",
            "N",
            "lbs",
            0.50,
            [{"label": "Flat", "acres": 100, "rate": 150}],
        )
        assert result.total_product == 15000.0
        assert result.total_cost == 7500.0


class TestAsAppliedComparison:
    def test_basic_comparison(self):
        rx_zones = [
            {"zone_id": 1, "rate": 120, "acres": 40},
            {"zone_id": 2, "rate": 160, "acres": 80},
        ]
        applied_zones = [
            {"zone_id": 1, "rate": 125},
            {"zone_id": 2, "rate": 155},
        ]
        result = as_applied_comparison("Field", "Urea", rx_zones, applied_zones)
        assert len(result.zones) == 2
        assert result.overall_accuracy_pct > 0
        # Zone 1 over-applied, zone 2 under-applied
        assert result.total_over_applied > 0
        assert result.total_under_applied > 0

    def test_perfect_application(self):
        rx_zones = [{"zone_id": 1, "rate": 100, "acres": 50}]
        applied_zones = [{"zone_id": 1, "rate": 100}]
        result = as_applied_comparison("F", "N", rx_zones, applied_zones)
        assert result.overall_accuracy_pct == 100.0
        assert result.total_over_applied == 0.0
        assert result.total_under_applied == 0.0


class TestCSVExport:
    def test_soil_test_csv(self):
        data = [{"p_ppm": 15, "k_ppm": 150}]
        summary = soil_test_summary("Field", 2024, data)
        content = soil_test_to_csv(summary)
        assert b"Field" in content
        assert b"p_ppm" in content

    def test_yield_csv(self):
        points = [{"yield": 180, "hybrid": "A"}, {"yield": 195, "hybrid": "B"}]
        result = yield_analysis("Field", 2024, points)
        content = yield_analysis_to_csv(result)
        assert b"Field" in content
        assert b"Overall Mean" in content

    def test_prescription_cost_csv(self):
        result = prescription_cost(
            "Rx",
            "N",
            "lbs",
            0.50,
            [{"label": "Zone1", "acres": 100, "rate": 150}],
        )
        content = prescription_cost_to_csv(result)
        assert b"Rx" in content
        assert b"Total Cost" in content
        # Parse as valid CSV
        reader = csv.reader(io.StringIO(content.decode()))
        rows = list(reader)
        assert len(rows) > 5
