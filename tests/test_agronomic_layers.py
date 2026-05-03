"""Tests for agronomic layer services — CDL, SSURGO, Weather/GDD."""

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from openfmis.services.cdl import (
    CDLCropRecord,
    CDLHistoryResult,
    _parse_cropscape_value,
    get_cdl_at_point,
    get_crop_name,
    summarize_crop_history,
)
from openfmis.services.ssurgo import (
    SoilComponent,
    SSURGOResult,
    summarize_soil,
)
from openfmis.services.weather import (
    DailyWeather,
    GDDResult,
    WeatherResult,
    accumulate_gdd,
    calculate_gdd,
    summarize_weather,
)

# ── CDL Tests ───────────────────────────────────────────────────────────


class TestCDLCropNames:
    def test_corn(self):
        assert get_crop_name(1) == "Corn"

    def test_soybeans(self):
        assert get_crop_name(5) == "Soybeans"

    def test_unknown(self):
        assert get_crop_name(9999) == "Unknown (9999)"


class TestCropscapeParser:
    def test_xml_format(self):
        xml = (
            "<GetCDLValueResponse>"
            "<Result>value=1,category=Corn,color=FFD300</Result>"
            "</GetCDLValueResponse>"
        )
        assert _parse_cropscape_value(xml) == 1

    def test_json_like_format(self):
        text = "Result: {'value': '5', 'category': 'Soybeans'}"
        assert _parse_cropscape_value(text) == 5

    def test_no_match(self):
        assert _parse_cropscape_value("gibberish") is None


class TestCDLSummary:
    def test_empty_result(self):
        result = CDLHistoryResult()
        summary = summarize_crop_history(result)
        assert summary["years"] == 0
        assert summary["crops"] == {}

    def test_crop_rotation(self):
        result = CDLHistoryResult(
            records=[
                CDLCropRecord(year=2020, crop_code=1, crop_name="Corn"),
                CDLCropRecord(year=2021, crop_code=5, crop_name="Soybeans"),
                CDLCropRecord(year=2022, crop_code=1, crop_name="Corn"),
                CDLCropRecord(year=2023, crop_code=5, crop_name="Soybeans"),
            ]
        )
        summary = summarize_crop_history(result)
        assert summary["years"] == 4
        assert summary["crops"]["Corn"] == 2
        assert summary["crops"]["Soybeans"] == 2
        assert len(summary["rotation"]) == 4
        assert summary["rotation"][0]["year"] == 2020

    def test_dominant_crop(self):
        result = CDLHistoryResult(
            records=[
                CDLCropRecord(year=2020, crop_code=1, crop_name="Corn"),
                CDLCropRecord(year=2021, crop_code=1, crop_name="Corn"),
                CDLCropRecord(year=2022, crop_code=5, crop_name="Soybeans"),
            ]
        )
        summary = summarize_crop_history(result)
        assert summary["dominant_crop"] == "Corn"


@pytest.mark.asyncio
class TestCDLQuery:
    async def test_get_cdl_at_point_success(self):
        mock_response = AsyncMock()
        mock_response.text = (
            "<GetCDLValueResponse>"
            "<Result>value=1,category=Corn,color=FFD300</Result>"
            "</GetCDLValueResponse>"
        )
        mock_response.raise_for_status = lambda: None

        with patch("openfmis.services.cdl.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            record = await get_cdl_at_point(40.1, -96.5, 2023)
            assert record is not None
            assert record.crop_code == 1
            assert record.crop_name == "Corn"
            assert record.year == 2023

    async def test_get_cdl_at_point_failure(self):
        with patch("openfmis.services.cdl.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = Exception("network error")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client.return_value = mock_instance

            record = await get_cdl_at_point(40.1, -96.5, 2023)
            assert record is None


# ── SSURGO Tests ────────────────────────────────────────────────────────


class TestSSURGOSummary:
    def test_empty_result(self):
        result = SSURGOResult()
        summary = summarize_soil(result)
        assert summary["components"] == 0

    def test_with_components(self):
        result = SSURGOResult(
            components=[
                SoilComponent(
                    mukey="12345",
                    musym="CrB",
                    muname="Crete silt loam",
                    compname="Crete",
                    comppct=75,
                    drainagecl="Moderately well drained",
                    hydgrp="B",
                    om_low=2.0,
                    om_high=4.0,
                    cec_low=15.0,
                    cec_high=25.0,
                    ph_low=6.1,
                    ph_high=7.3,
                ),
                SoilComponent(
                    mukey="12346",
                    musym="HsA",
                    muname="Hastings silt loam",
                    compname="Hastings",
                    comppct=25,
                    drainagecl="Well drained",
                    hydgrp="B",
                    om_low=1.5,
                    om_high=3.0,
                    cec_low=12.0,
                    cec_high=20.0,
                    ph_low=6.5,
                    ph_high=7.5,
                ),
            ],
            dominant_component="Crete",
            dominant_drainage="Moderately well drained",
            dominant_hydgrp="B",
        )
        summary = summarize_soil(result)
        assert summary["components"] == 2
        assert summary["dominant_component"] == "Crete"
        assert summary["weighted_om_pct"] is not None
        assert summary["weighted_cec"] is not None
        assert summary["weighted_ph"] is not None
        assert "Crete" in summary["soil_names"]
        assert "Hastings" in summary["soil_names"]

    def test_weighted_average(self):
        result = SSURGOResult(
            components=[
                SoilComponent(
                    mukey="1",
                    musym="A",
                    muname="Soil A",
                    compname="A",
                    comppct=80,
                    om_low=2.0,
                    om_high=2.0,
                ),
                SoilComponent(
                    mukey="2",
                    musym="B",
                    muname="Soil B",
                    compname="B",
                    comppct=20,
                    om_low=4.0,
                    om_high=4.0,
                ),
            ],
        )
        summary = summarize_soil(result)
        # Weighted: (2.0*80 + 4.0*20) / 100 = 2.4
        assert summary["weighted_om_pct"] == 2.4


# ── Weather / GDD Tests ────────────────────────────────────────────────


class TestGDDCalculation:
    def test_basic_gdd(self):
        """Standard warm day — corn base 50°F."""
        gdd = calculate_gdd(80.0, 60.0, base_f=50.0, upper_f=86.0)
        # (80+60)/2 - 50 = 20
        assert gdd == 20.0

    def test_cold_day_zero(self):
        """Both temps below base → 0 GDD."""
        gdd = calculate_gdd(45.0, 30.0, base_f=50.0)
        assert gdd == 0.0

    def test_upper_cap(self):
        """Max temp capped at upper limit."""
        gdd = calculate_gdd(95.0, 70.0, base_f=50.0, upper_f=86.0)
        # max capped to 86, min stays 70: (86+70)/2 - 50 = 28
        assert gdd == 28.0

    def test_min_capped_at_base(self):
        """Min temp capped at base."""
        gdd = calculate_gdd(70.0, 40.0, base_f=50.0, upper_f=86.0)
        # min capped to 50: (70+50)/2 - 50 = 10
        assert gdd == 10.0

    def test_no_upper_cap(self):
        """Simple GDD without upper limit."""
        gdd = calculate_gdd(95.0, 70.0, base_f=50.0, upper_f=None)
        # No cap: (95+70)/2 - 50 = 32.5
        assert gdd == 32.5

    def test_wheat_base(self):
        """Wheat uses base 32°F."""
        gdd = calculate_gdd(60.0, 40.0, base_f=32.0, upper_f=None)
        # (60+40)/2 - 32 = 18
        assert gdd == 18.0


class TestGDDAccumulation:
    def test_accumulate(self):
        temps = [
            (date(2024, 5, 1), 75.0, 55.0),
            (date(2024, 5, 2), 80.0, 60.0),
            (date(2024, 5, 3), 70.0, 50.0),
        ]
        result = accumulate_gdd(temps, base_f=50.0, upper_f=86.0)
        assert isinstance(result, GDDResult)
        # Day 1: (75+55)/2 - 50 = 15
        # Day 2: (80+60)/2 - 50 = 20
        # Day 3: (70+50)/2 - 50 = 10
        assert result.total_gdd == 45.0
        assert len(result.daily_gdd) == 3
        assert result.start_date == date(2024, 5, 1)
        assert result.end_date == date(2024, 5, 3)

    def test_empty_temps(self):
        result = accumulate_gdd([], base_f=50.0)
        assert result.total_gdd == 0.0
        assert len(result.daily_gdd) == 0


class TestWeatherSummary:
    def test_summary(self):
        result = WeatherResult(
            daily=[
                DailyWeather(
                    date=date(2024, 5, 1),
                    temp_max_f=75,
                    temp_min_f=55,
                    precip_in=0.5,
                    gdd=15,
                ),
                DailyWeather(
                    date=date(2024, 5, 2),
                    temp_max_f=80,
                    temp_min_f=60,
                    precip_in=0.0,
                    gdd=20,
                ),
                DailyWeather(
                    date=date(2024, 5, 3),
                    temp_max_f=70,
                    temp_min_f=50,
                    precip_in=0.1,
                    gdd=10,
                ),
            ],
            cumulative_gdd=45.0,
            total_precip_in=0.6,
            avg_temp_f=65.0,
        )
        summary = summarize_weather(result)
        assert summary["days"] == 3
        assert summary["cumulative_gdd"] == 45.0
        assert summary["max_temp_f"] == 80
        assert summary["min_temp_f"] == 50
        assert summary["rainy_days"] == 2
        assert summary["max_daily_precip_in"] == 0.5

    def test_empty_summary(self):
        result = WeatherResult()
        summary = summarize_weather(result)
        assert summary["days"] == 0
