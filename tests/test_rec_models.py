"""University nutrient recommendation model tests."""

import pytest

from openfmis.services.rec_models import (
    Nutrient,
    PreviousCrop,
    RecInput,
    SoilTexture,
    mrtn_nitrogen,
    recommend,
    tristate_phosphorus,
    tristate_potassium,
    umn_nitrogen,
)

# ── MRTN (Illinois / Iowa) ──────────────────────────────────────────────


class TestMRTN:
    def test_corn_after_soybean_il(self):
        rec = mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=5.50, n_price=0.50, state="IL")
        assert rec.nutrient == Nutrient.N
        assert rec.model == "MRTN-IL"
        assert 100 < rec.rate_lbs_ac < 250

    def test_corn_after_corn_il(self):
        rec = mrtn_nitrogen(PreviousCrop.CORN, corn_price=5.50, n_price=0.50, state="IL")
        # Corn-on-corn needs more N than corn after soybean
        rec_soy = mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=5.50, n_price=0.50, state="IL")
        assert rec.rate_lbs_ac > rec_soy.rate_lbs_ac

    def test_iowa(self):
        rec = mrtn_nitrogen(PreviousCrop.SOYBEAN, state="IA")
        assert rec.model == "MRTN-IA"
        assert 100 < rec.rate_lbs_ac < 250

    def test_high_n_price_lowers_rate(self):
        """Expensive N → lower economic optimum."""
        rec_cheap = mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=5.0, n_price=0.30)
        rec_expensive = mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=5.0, n_price=0.80)
        assert rec_cheap.rate_lbs_ac > rec_expensive.rate_lbs_ac

    def test_invalid_state(self):
        with pytest.raises(ValueError, match="IL and IA"):
            mrtn_nitrogen(PreviousCrop.SOYBEAN, state="TX")

    def test_zero_corn_price(self):
        with pytest.raises(ValueError, match="positive"):
            mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=0)

    def test_rate_in_bounds(self):
        """Rate should be between 50 and 250 lbs/ac."""
        rec = mrtn_nitrogen(PreviousCrop.SOYBEAN, corn_price=5.0, n_price=0.50)
        assert 50 <= rec.rate_lbs_ac <= 250


# ── Tri-State P ──────────────────────────────────────────────────────────


class TestTriStateP:
    def test_below_critical(self):
        rec = tristate_phosphorus(soil_test_p_ppm=10, crop="corn", yield_goal=200)
        assert rec.nutrient == Nutrient.P2O5
        assert rec.model == "Tri-State"
        # Below critical → buildup + maintenance, should be higher
        assert rec.rate_lbs_ac > 74  # maintenance alone is ~74

    def test_at_critical(self):
        rec = tristate_phosphorus(soil_test_p_ppm=20, crop="corn", yield_goal=200)
        # At critical → maintenance only
        assert rec.rate_lbs_ac == pytest.approx(0.37 * 200, abs=1)

    def test_well_above_critical(self):
        rec = tristate_phosphorus(soil_test_p_ppm=45, crop="corn", yield_goal=200)
        assert rec.rate_lbs_ac == 0.0

    def test_soybean(self):
        rec = tristate_phosphorus(soil_test_p_ppm=10, crop="soybean", yield_goal=60)
        assert rec.rate_lbs_ac > 0

    def test_invalid_crop(self):
        with pytest.raises(ValueError, match="corn/soybean"):
            tristate_phosphorus(soil_test_p_ppm=10, crop="wheat")


# ── Tri-State K ──────────────────────────────────────────────────────────


class TestTriStateK:
    def test_below_critical(self):
        rec = tristate_potassium(soil_test_k_ppm=80, crop="corn", yield_goal=200)
        assert rec.nutrient == Nutrient.K2O
        assert rec.rate_lbs_ac > 54  # maintenance alone

    def test_at_critical(self):
        rec = tristate_potassium(soil_test_k_ppm=120, crop="corn", yield_goal=200)
        # At critical (medium CEC default) → maintenance only
        assert rec.rate_lbs_ac == pytest.approx(0.27 * 200, abs=1)

    def test_well_above_critical(self):
        rec = tristate_potassium(soil_test_k_ppm=200, crop="corn", yield_goal=200)
        assert rec.rate_lbs_ac == 0.0

    def test_low_cec_lower_critical(self):
        """Low CEC soils have lower critical K level."""
        rec_low = tristate_potassium(soil_test_k_ppm=105, crop="corn", yield_goal=200, cec=8)
        rec_high = tristate_potassium(soil_test_k_ppm=105, crop="corn", yield_goal=200, cec=25)
        # 105 is above low-CEC critical (100) but below high-CEC critical (130)
        assert rec_low.rate_lbs_ac < rec_high.rate_lbs_ac

    def test_soybean(self):
        rec = tristate_potassium(soil_test_k_ppm=80, crop="soybean", yield_goal=60)
        assert rec.rate_lbs_ac > 0

    def test_invalid_crop(self):
        with pytest.raises(ValueError, match="corn/soybean"):
            tristate_potassium(soil_test_k_ppm=80, crop="wheat")


# ── UMN (Minnesota) ─────────────────────────────────────────────────────


class TestUMN:
    def test_basic(self):
        rec = umn_nitrogen(yield_goal=200, previous_crop=PreviousCrop.SOYBEAN)
        assert rec.nutrient == Nutrient.N
        assert rec.model == "UMN"
        assert rec.rate_lbs_ac > 0

    def test_soybean_credit(self):
        """Corn after soybean should need less N than corn after corn."""
        rec_soy = umn_nitrogen(yield_goal=200, previous_crop=PreviousCrop.SOYBEAN)
        rec_corn = umn_nitrogen(yield_goal=200, previous_crop=PreviousCrop.CORN)
        assert rec_soy.rate_lbs_ac < rec_corn.rate_lbs_ac

    def test_alfalfa_large_credit(self):
        rec = umn_nitrogen(yield_goal=200, previous_crop=PreviousCrop.ALFALFA)
        # Alfalfa gives ~150 lb credit
        assert rec.rate_lbs_ac < 100

    def test_om_credit(self):
        """High OM should reduce N rate."""
        rec_low_om = umn_nitrogen(yield_goal=200, soil_om_pct=2.0)
        rec_high_om = umn_nitrogen(yield_goal=200, soil_om_pct=5.0)
        assert rec_high_om.rate_lbs_ac < rec_low_om.rate_lbs_ac

    def test_sandy_soil_higher_rate(self):
        rec_sand = umn_nitrogen(yield_goal=200, soil_texture=SoilTexture.SAND)
        rec_clay = umn_nitrogen(yield_goal=200, soil_texture=SoilTexture.CLAY)
        assert rec_sand.rate_lbs_ac > rec_clay.rate_lbs_ac

    def test_rate_in_bounds(self):
        rec = umn_nitrogen(yield_goal=200)
        assert 0 <= rec.rate_lbs_ac <= 250

    def test_high_yield_goal(self):
        rec = umn_nitrogen(yield_goal=250)
        assert rec.rate_lbs_ac > umn_nitrogen(yield_goal=150).rate_lbs_ac


# ── Unified recommend() ─────────────────────────────────────────────────


class TestRecommend:
    def test_mrtn_il(self):
        inputs = RecInput(previous_crop=PreviousCrop.SOYBEAN)
        rec = recommend("mrtn-il", "N", inputs)
        assert rec.model == "MRTN-IL"

    def test_mrtn_ia(self):
        inputs = RecInput(previous_crop=PreviousCrop.CORN)
        rec = recommend("mrtn-ia", "N", inputs)
        assert rec.model == "MRTN-IA"

    def test_tristate_p(self):
        inputs = RecInput(soil_test_p_ppm=15, yield_goal=200)
        rec = recommend("tri-state", "P2O5", inputs)
        assert rec.nutrient == Nutrient.P2O5

    def test_tristate_k(self):
        inputs = RecInput(soil_test_k_ppm=90, yield_goal=200)
        rec = recommend("tri-state", "K2O", inputs)
        assert rec.nutrient == Nutrient.K2O

    def test_umn(self):
        inputs = RecInput(yield_goal=200, soil_om_pct=4.0)
        rec = recommend("umn", "N", inputs)
        assert rec.model == "UMN"

    def test_mrtn_wrong_nutrient(self):
        with pytest.raises(ValueError, match="only supports N"):
            recommend("mrtn-il", "P2O5", RecInput())

    def test_tristate_wrong_nutrient(self):
        with pytest.raises(ValueError, match="P2O5 and K2O"):
            recommend("tri-state", "N", RecInput())

    def test_umn_wrong_nutrient(self):
        with pytest.raises(ValueError, match="only supports N"):
            recommend("umn", "K2O", RecInput())

    def test_unknown_model(self):
        with pytest.raises(ValueError, match="Unknown model"):
            recommend("purdue-special", "N", RecInput())

    def test_tristate_p_missing_soil_test(self):
        with pytest.raises(ValueError, match="soil_test_p_ppm"):
            recommend("tri-state", "P2O5", RecInput())

    def test_tristate_k_missing_soil_test(self):
        with pytest.raises(ValueError, match="soil_test_k_ppm"):
            recommend("tri-state", "K2O", RecInput())
