"""Band registry — maps satellite collection band names to common names.

Each CollectionProfile defines how to read bands from a specific data source.
Supports optical (Sentinel-2, Landsat) and SAR (Sentinel-1) collections,
plus custom user uploads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CollectionProfile:
    collection_id: str
    display_name: str
    sensor_type: Literal["optical", "sar", "custom"]
    stac_endpoint: str | None  # None for custom uploads
    stac_collection: str | None
    # Maps STAC asset key → common band name
    band_map: dict[str, str]
    scale_factor: float = 1.0
    scale_offset: float = 0.0
    nodata_value: float = 0.0
    description: str = ""


# ── Sentinel-2 Level 2A ──────────────────────────────────────────────────────

SENTINEL2_L2A = CollectionProfile(
    collection_id="sentinel-2-l2a",
    display_name="Sentinel-2 L2A",
    sensor_type="optical",
    stac_endpoint="https://earth-search.aws.element84.com/v1",
    stac_collection="sentinel-2-l2a",
    band_map={
        "coastal": "coastal",  # B01 - 60m
        "blue": "blue",  # B02 - 10m
        "green": "green",  # B03 - 10m
        "red": "red",  # B04 - 10m
        "rededge1": "rededge1",  # B05 - 20m
        "rededge2": "rededge2",  # B06 - 20m
        "rededge3": "rededge3",  # B07 - 20m
        "nir": "nir",  # B08 - 10m
        "nir08": "nir",  # B8A - 20m (alternate NIR)
        "nir09": "nir09",  # B09 - 60m water vapor
        "swir16": "swir16",  # B11 - 20m
        "swir22": "swir22",  # B12 - 20m
        "scl": "scl",  # Scene Classification Layer
    },
    scale_factor=1.0 / 10000.0,  # Sentinel-2 L2A reflectance is 0-10000
    nodata_value=0.0,
    description="ESA Sentinel-2 Level 2A surface reflectance via AWS Element84 STAC",
)

# ── Sentinel-1 GRD ───────────────────────────────────────────────────────────

SENTINEL1_GRD = CollectionProfile(
    collection_id="sentinel-1-grd",
    display_name="Sentinel-1 GRD",
    sensor_type="sar",
    stac_endpoint="https://earth-search.aws.element84.com/v1",
    stac_collection="sentinel-1-grd",
    band_map={
        "vv": "vv",
        "vh": "vh",
    },
    scale_factor=1.0,  # Already in dB or linear power
    nodata_value=0.0,
    description="ESA Sentinel-1 Ground Range Detected C-band SAR via AWS",
)

# ── Landsat Collection 2 Level 2 ─────────────────────────────────────────────

LANDSAT_C2_L2 = CollectionProfile(
    collection_id="landsat-c2-l2",
    display_name="Landsat 8/9 C2 L2",
    sensor_type="optical",
    stac_endpoint="https://earth-search.aws.element84.com/v1",
    stac_collection="landsat-c2-l2",
    band_map={
        "coastal": "coastal",  # B1 - 30m
        "blue": "blue",  # B2 - 30m
        "green": "green",  # B3 - 30m
        "red": "red",  # B4 - 30m
        "nir08": "nir",  # B5 - 30m
        "swir16": "swir16",  # B6 - 30m
        "swir22": "swir22",  # B7 - 30m
        "lwir11": "lwir11",  # B10 - thermal 100m
        "lwir12": "lwir12",  # B11 - thermal 100m (Landsat 8 only)
    },
    scale_factor=0.0000275,
    scale_offset=-0.2,
    nodata_value=0.0,
    description="USGS Landsat 8/9 Collection 2 Level 2 surface reflectance via AWS",
)

# ── Custom user uploads ──────────────────────────────────────────────────────

CUSTOM_UPLOAD = CollectionProfile(
    collection_id="custom-upload",
    display_name="Custom Upload",
    sensor_type="custom",
    stac_endpoint=None,
    stac_collection=None,
    band_map={},  # User-defined at upload time
    scale_factor=1.0,
    nodata_value=0.0,
    description="User-uploaded imagery (drone, aerial, other satellite)",
)

# ── Registry ──────────────────────────────────────────────────────────────────

_PROFILES: dict[str, CollectionProfile] = {
    p.collection_id: p for p in [SENTINEL2_L2A, SENTINEL1_GRD, LANDSAT_C2_L2, CUSTOM_UPLOAD]
}


def get_profile(collection_id: str) -> CollectionProfile:
    """Get a collection profile by ID. Raises KeyError if unknown."""
    if collection_id not in _PROFILES:
        raise KeyError(
            f"Unknown collection: {collection_id!r}. Available: {sorted(_PROFILES.keys())}"
        )
    return _PROFILES[collection_id]


def list_profiles() -> list[CollectionProfile]:
    """Return all registered collection profiles."""
    return list(_PROFILES.values())


def get_common_band_name(collection_id: str, asset_key: str) -> str | None:
    """Map a STAC asset key to a common band name for a given collection."""
    profile = _PROFILES.get(collection_id)
    if profile is None:
        return None
    return profile.band_map.get(asset_key)


def get_available_bands(collection_id: str) -> list[str]:
    """Return sorted list of common band names available for a collection."""
    profile = _PROFILES.get(collection_id)
    if profile is None:
        return []
    return sorted(set(profile.band_map.values()))
