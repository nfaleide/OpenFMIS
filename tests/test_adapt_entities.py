"""Tests for ADAPT entity type mapping and structured export helpers."""

from openfmis.services.adapt_export import (
    _adapt_type_for_event,
    _build_applied_operation,
    _build_harvest_observation,
    _build_soil_sample,
    _soil_unit,
)


class TestAdaptTypeMapping:
    def test_soil_testing(self):
        assert _adapt_type_for_event("soil_testing") == "SoilSample"

    def test_harvest(self):
        assert _adapt_type_for_event("harvest") == "HarvestObservation"

    def test_crop_protection(self):
        assert _adapt_type_for_event("crop_protection") == "AppliedOperation"

    def test_fertilizing(self):
        assert _adapt_type_for_event("fertilizing") == "AppliedOperation"

    def test_planting(self):
        assert _adapt_type_for_event("planting") == "PlantingOperation"

    def test_tillage(self):
        assert _adapt_type_for_event("tillage") == "TillageOperation"

    def test_unknown_defaults_to_field_activity(self):
        assert _adapt_type_for_event("custom_type") == "FieldActivity"


class TestSoilSampleBuilder:
    def test_basic(self):
        base = {"type": "FieldActivity", "event_type": "soil_testing", "version": 1}
        data = {
            "test_entries": [
                {"p_ppm": 15, "k_ppm": 150, "ph": 6.5, "depth": "0-6"},
                {"p_ppm": 20, "k_ppm": 180, "ph": 6.8},
            ]
        }
        result = _build_soil_sample(base, data)
        assert result["type"] == "SoilSample"
        assert result["sample_count"] == 2
        assert len(result["analytes"]) > 0
        assert result["depth"] == "0-6"

    def test_empty_data(self):
        base = {"type": "FieldActivity"}
        result = _build_soil_sample(base, None)
        assert result["type"] == "SoilSample"
        assert "analytes" not in result

    def test_analyte_units(self):
        base = {"type": "FieldActivity"}
        data = {"test_entries": [{"p_ppm": 15, "om_pct": 3.2, "ph": 6.5}]}
        result = _build_soil_sample(base, data)
        units = {a["analyte"]: a["unit"] for a in result["analytes"]}
        assert units["p_ppm"] == "ppm"
        assert units["om_pct"] == "%"
        assert units["ph"] == ""


class TestHarvestObservationBuilder:
    def test_basic(self):
        base = {"type": "FieldActivity", "event_type": "harvest"}
        data = {
            "yield_value": 195.5,
            "yield_unit": "bu/ac",
            "moisture_pct": 15.2,
            "hybrid": "DKC62-08",
            "crop": "Corn",
        }
        result = _build_harvest_observation(base, data)
        assert result["type"] == "HarvestObservation"
        assert result["yield_value"] == 195.5
        assert result["hybrid"] == "DKC62-08"

    def test_empty_data(self):
        base = {"type": "FieldActivity"}
        result = _build_harvest_observation(base, None)
        assert result["type"] == "HarvestObservation"
        assert "yield_value" not in result


class TestAppliedOperationBuilder:
    def test_basic(self):
        base = {"type": "FieldActivity", "event_type": "crop_protection"}
        data = {
            "products": [
                {
                    "product_name": "Roundup PowerMax",
                    "rate": 32,
                    "rate_unit": "oz/ac",
                    "total_applied": 640,
                },
            ],
            "target_pest": "broadleaf weeds",
            "application_method": "broadcast",
        }
        result = _build_applied_operation(base, data)
        assert result["type"] == "AppliedOperation"
        assert len(result["products"]) == 1
        assert result["products"][0]["product_name"] == "Roundup PowerMax"
        assert result["target_pest"] == "broadleaf weeds"

    def test_empty_products(self):
        base = {"type": "FieldActivity"}
        result = _build_applied_operation(base, {"products": []})
        assert result["products"] == []


class TestSoilUnits:
    def test_ppm(self):
        assert _soil_unit("p_ppm") == "ppm"

    def test_pct(self):
        assert _soil_unit("om_pct") == "%"

    def test_meq(self):
        assert _soil_unit("cec_meq") == "meq/100g"

    def test_ph(self):
        assert _soil_unit("ph") == ""

    def test_default(self):
        assert _soil_unit("zinc") == "ppm"
