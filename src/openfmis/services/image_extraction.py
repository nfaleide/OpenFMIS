"""ImageExtractionService — read COG/GeoTIFF bands and compute spectral indices.

Supports multiple data sources:
- Remote COGs (Sentinel-2, Sentinel-1, Landsat) via HTTP
- Local files (custom user uploads)

Rasterio is synchronous; all heavy I/O runs in asyncio.to_thread().
Index computation uses the configurable BandMathEngine.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numpy as np

from openfmis.services.band_math import evaluate as evaluate_formula
from openfmis.services.band_math import extract_required_bands
from openfmis.services.band_registry import SENTINEL2_L2A, get_profile

log = logging.getLogger(__name__)

# Legacy index → formula mapping (for backward compat with existing jobs)
_LEGACY_INDEX_FORMULAS = {
    "ndvi": "(nir - red) / (nir + red)",
    "ndwi": "(green - nir) / (green + nir)",
    "evi": "2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)",
    "ndre": "(nir - rededge1) / (nir + rededge1)",
    "savi": "(nir - red) * 1.5 / (nir + red + 0.5)",
}


def _result_stats(index_arr: np.ndarray) -> dict[str, Any]:
    """Compute summary statistics over a 2-D index array (may contain NaN/nodata)."""
    flat = index_arr.flatten()
    total = flat.size
    valid = flat[np.isfinite(flat)]
    valid_count = valid.size

    if valid_count == 0:
        return {
            "mean": None,
            "min": None,
            "max": None,
            "std": None,
            "p10": None,
            "p90": None,
            "pixel_count": total,
            "valid_pixel_count": 0,
            "nodata_fraction": 1.0,
        }

    return {
        "mean": float(np.mean(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "std": float(np.std(valid)),
        "p10": float(np.percentile(valid, 10)),
        "p90": float(np.percentile(valid, 90)),
        "pixel_count": total,
        "valid_pixel_count": valid_count,
        "nodata_fraction": round(1.0 - valid_count / total, 4),
    }


def _read_band_sync(
    href: str,
    geojson_geometry: dict,
    scale_factor: float = 1.0 / 10000.0,
    scale_offset: float = 0.0,
    nodata_value: float = 0.0,
    band_index: int | None = None,
) -> np.ndarray:
    """Synchronous: open a COG/GeoTIFF and read within *geojson_geometry*.

    Handles both remote HTTP COGs and local file paths.
    For multi-band files, band_index selects which band to read (1-based).
    """
    import rasterio
    from rasterio.mask import mask as rio_mask

    is_remote = href.startswith("http://") or href.startswith("https://")

    # Handle band index encoded in href (e.g., "/path/file.tif#3")
    if "#" in href and not is_remote:
        href, idx_str = href.rsplit("#", 1)
        band_index = int(idx_str)

    env_kwargs = {}
    if is_remote:
        env_kwargs = {
            "AWS_NO_SIGN_REQUEST": "YES",
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
        }

    with rasterio.Env(**env_kwargs):
        with rasterio.open(href) as src:
            indexes = [band_index] if band_index else [1]
            out_image, _ = rio_mask(
                src,
                [geojson_geometry],
                crop=True,
                nodata=nodata_value,
                filled=True,
                indexes=indexes,
            )
            data = out_image[0].astype(np.float64)
            # Apply scale factor and offset
            data = data * scale_factor + scale_offset
            # Mask nodata
            data = np.where(data <= nodata_value * scale_factor + scale_offset, np.nan, data)
    return data


async def extract_and_compute(
    index_type: str,
    assets: dict[str, str],
    geojson_geometry: dict,
    formula: str | None = None,
    required_bands: list[str] | None = None,
    parameters: dict[str, float] | None = None,
    collection: str = "sentinel-2-l2a",
) -> dict[str, Any]:
    """Read required bands asynchronously, compute index, return statistics.

    If formula is provided, uses BandMathEngine. Otherwise falls back to
    the formula for index_type from the builtin registry or legacy map.
    """
    # Resolve formula
    if formula is None:
        formula = _LEGACY_INDEX_FORMULAS.get(index_type)
        if formula is None:
            # Try to find in builtin indices
            from openfmis.services.band_math import BUILTIN_INDICES

            for idx in BUILTIN_INDICES:
                if idx["slug"] == index_type:
                    formula = idx["formula"]
                    parameters = parameters or idx.get("parameters")
                    break
        if formula is None:
            raise ValueError(f"Unknown index type and no formula provided: {index_type}")

    # Resolve required bands from formula
    if required_bands is None:
        required_bands = extract_required_bands(formula)

    # Get collection profile for scaling
    try:
        profile = get_profile(collection)
    except KeyError:
        profile = SENTINEL2_L2A  # fallback

    # Resolve asset hrefs for each required band
    hrefs: dict[str, str] = {}
    for band_key in required_bands:
        if band_key not in assets:
            raise ValueError(
                f"Scene assets missing band '{band_key}' required for {index_type}. "
                f"Available: {list(assets.keys())}"
            )
        hrefs[band_key] = assets[band_key]

    # Read all bands concurrently in a thread pool
    results = await asyncio.gather(
        *(
            asyncio.to_thread(
                _read_band_sync,
                href,
                geojson_geometry,
                scale_factor=profile.scale_factor,
                scale_offset=profile.scale_offset,
                nodata_value=profile.nodata_value,
            )
            for href in hrefs.values()
        )
    )
    band_arrays: dict[str, np.ndarray] = {}
    for band_key, arr in zip(hrefs.keys(), results):
        band_arrays[band_key] = arr

    # Compute index using band math engine
    index_arr = evaluate_formula(formula, band_arrays, parameters)
    return _result_stats(index_arr)
