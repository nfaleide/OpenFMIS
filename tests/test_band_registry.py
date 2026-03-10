"""Tests for the band registry — collection profiles and band mappings."""

import pytest

from openfmis.services.band_registry import (
    get_available_bands,
    get_common_band_name,
    get_profile,
    list_profiles,
)


class TestGetProfile:
    def test_sentinel2(self):
        p = get_profile("sentinel-2-l2a")
        assert p.sensor_type == "optical"
        assert p.scale_factor == 1.0 / 10000.0

    def test_sentinel1(self):
        p = get_profile("sentinel-1-grd")
        assert p.sensor_type == "sar"
        assert "vv" in p.band_map

    def test_landsat(self):
        p = get_profile("landsat-c2-l2")
        assert p.sensor_type == "optical"
        assert p.scale_offset == -0.2

    def test_custom(self):
        p = get_profile("custom-upload")
        assert p.sensor_type == "custom"
        assert p.stac_endpoint is None

    def test_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown collection"):
            get_profile("nonexistent")


class TestListProfiles:
    def test_returns_all(self):
        profiles = list_profiles()
        assert len(profiles) == 4
        ids = {p.collection_id for p in profiles}
        assert "sentinel-2-l2a" in ids
        assert "sentinel-1-grd" in ids
        assert "landsat-c2-l2" in ids
        assert "custom-upload" in ids


class TestGetCommonBandName:
    def test_sentinel2_nir(self):
        assert get_common_band_name("sentinel-2-l2a", "nir") == "nir"
        assert get_common_band_name("sentinel-2-l2a", "nir08") == "nir"

    def test_sentinel1_vv(self):
        assert get_common_band_name("sentinel-1-grd", "vv") == "vv"

    def test_unknown_asset(self):
        assert get_common_band_name("sentinel-2-l2a", "nonexistent") is None

    def test_unknown_collection(self):
        assert get_common_band_name("fake", "nir") is None


class TestGetAvailableBands:
    def test_sentinel2_bands(self):
        bands = get_available_bands("sentinel-2-l2a")
        assert "nir" in bands
        assert "red" in bands
        assert "swir16" in bands

    def test_sentinel1_bands(self):
        bands = get_available_bands("sentinel-1-grd")
        assert sorted(bands) == ["vh", "vv"]

    def test_landsat_bands(self):
        bands = get_available_bands("landsat-c2-l2")
        assert "nir" in bands
        assert "blue" in bands

    def test_custom_empty(self):
        assert get_available_bands("custom-upload") == []

    def test_unknown_empty(self):
        assert get_available_bands("nonexistent") == []
