"""USDA Cropland Data Layer (CDL) service.

Queries the USDA CropScape API to retrieve crop history for field
boundaries.  CDL provides annual 30-meter crop classification rasters
for the continental US from 2008 to present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from shapely.geometry import shape as shapely_shape

log = logging.getLogger(__name__)

# CropScape API base — no API key required
CROPSCAPE_BASE = "https://nassgeodata.gmu.edu/axis2/services/CDLService"

# CDL crop code → common name mapping (subset of most common US row crops)
CDL_CROP_NAMES: dict[int, str] = {
    1: "Corn",
    2: "Cotton",
    3: "Rice",
    4: "Sorghum",
    5: "Soybeans",
    6: "Sunflower",
    10: "Peanuts",
    11: "Tobacco",
    12: "Sweet Corn",
    13: "Pop or Orn Corn",
    21: "Barley",
    22: "Durum Wheat",
    23: "Spring Wheat",
    24: "Winter Wheat",
    25: "Other Small Grains",
    26: "Dbl Crop WinWht/Soybeans",
    27: "Rye",
    28: "Oats",
    29: "Millet",
    30: "Speltz",
    31: "Canola",
    32: "Flaxseed",
    33: "Safflower",
    34: "Rape Seed",
    35: "Mustard",
    36: "Alfalfa",
    37: "Other Hay/Non Alfalfa",
    38: "Camelina",
    39: "Buckwheat",
    41: "Sugarbeets",
    42: "Dry Beans",
    43: "Potatoes",
    44: "Other Crops",
    45: "Sugarcane",
    46: "Sweet Potatoes",
    47: "Misc Vegs & Fruits",
    48: "Watermelons",
    49: "Onions",
    50: "Cucumbers",
    51: "Chick Peas",
    52: "Lentils",
    53: "Peas",
    54: "Tomatoes",
    55: "Caneberries",
    56: "Hops",
    57: "Herbs",
    58: "Clover/Wildflowers",
    59: "Sod/Grass Seed",
    60: "Switchgrass",
    61: "Fallow/Idle Cropland",
    63: "Forest",
    64: "Shrubland",
    65: "Barren",
    66: "Cherries",
    67: "Peaches",
    68: "Apples",
    69: "Grapes",
    70: "Christmas Trees",
    71: "Other Tree Crops",
    72: "Citrus",
    74: "Pecans",
    75: "Almonds",
    76: "Walnuts",
    77: "Pears",
    111: "Open Water",
    121: "Developed/Open Space",
    122: "Developed/Low Intensity",
    123: "Developed/Med Intensity",
    124: "Developed/High Intensity",
    131: "Barren",
    141: "Deciduous Forest",
    142: "Evergreen Forest",
    143: "Mixed Forest",
    152: "Shrubland",
    176: "Grassland/Pasture",
    190: "Woody Wetlands",
    195: "Herbaceous Wetlands",
    204: "Pistachios",
    205: "Triticale",
    206: "Carrots",
    207: "Asparagus",
    208: "Garlic",
    209: "Cantaloupes",
    210: "Prunes",
    211: "Olives",
    212: "Oranges",
    213: "Honeydew Melons",
    214: "Broccoli",
    215: "Avocados",
    216: "Peppers",
    217: "Pomegranates",
    218: "Nectarines",
    219: "Greens",
    220: "Plums",
    221: "Strawberries",
    222: "Squash",
    223: "Apricots",
    224: "Vetch",
    225: "Dbl Crop WinWht/Corn",
    226: "Dbl Crop Oats/Corn",
    227: "Lettuce",
    229: "Pumpkins",
    230: "Dbl Crop Lettuce/Durum Wht",
    231: "Dbl Crop Lettuce/Cantaloupe",
    232: "Dbl Crop Lettuce/Cotton",
    233: "Dbl Crop Lettuce/Barley",
    234: "Dbl Crop Durum Wht/Sorghum",
    235: "Dbl Crop Barley/Sorghum",
    236: "Dbl Crop WinWht/Sorghum",
    237: "Dbl Crop Barley/Corn",
    238: "Dbl Crop WinWht/Cotton",
    239: "Dbl Crop Soybeans/Cotton",
    240: "Dbl Crop Soybeans/Oats",
    241: "Dbl Crop Corn/Soybeans",
    242: "Blueberries",
    243: "Cabbage",
    244: "Cauliflower",
    245: "Celery",
    246: "Radishes",
    247: "Turnips",
    248: "Eggplants",
    249: "Gourds",
    250: "Cranberries",
    254: "Dbl Crop Barley/Soybeans",
}


@dataclass
class CDLCropRecord:
    """Crop classification for one year at a location."""

    year: int
    crop_code: int
    crop_name: str
    acreage: float | None = None
    percent_cover: float | None = None


@dataclass
class CDLHistoryResult:
    """Multi-year crop history for a field or point."""

    records: list[CDLCropRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    centroid_lat: float | None = None
    centroid_lon: float | None = None


def get_crop_name(code: int) -> str:
    """Look up CDL crop name from code."""
    return CDL_CROP_NAMES.get(code, f"Unknown ({code})")


async def get_cdl_at_point(
    lat: float,
    lon: float,
    year: int,
    timeout: float = 15.0,
) -> CDLCropRecord | None:
    """Query CropScape for the crop at a specific lat/lon and year.

    Returns None if the API call fails or returns no data.
    """
    url = f"{CROPSCAPE_BASE}/GetCDLValue"
    params = {
        "year": str(year),
        "lat": str(lat),
        "lon": str(lon),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.text

            # Response format: "Result: {'value': '1', ...}" or similar
            # Parse the crop code from the response
            code = _parse_cropscape_value(data)
            if code is not None:
                return CDLCropRecord(
                    year=year,
                    crop_code=code,
                    crop_name=get_crop_name(code),
                )
    except Exception as exc:
        log.warning("CDL query failed for (%s, %s) year %d: %s", lat, lon, year, exc)

    return None


async def get_crop_history(
    geometry_geojson: dict[str, Any],
    start_year: int = 2018,
    end_year: int = 2024,
    timeout: float = 15.0,
) -> CDLHistoryResult:
    """Get multi-year crop history for a field boundary.

    Queries CDL at the field centroid for each year in the range.

    Args:
        geometry_geojson: GeoJSON geometry (Polygon or MultiPolygon).
        start_year: First year to query.
        end_year: Last year to query (inclusive).
        timeout: HTTP timeout per request.

    Returns:
        CDLHistoryResult with one record per year.
    """
    result = CDLHistoryResult()

    geom = shapely_shape(geometry_geojson)
    centroid = geom.centroid
    result.centroid_lat = centroid.y
    result.centroid_lon = centroid.x

    for year in range(start_year, end_year + 1):
        record = await get_cdl_at_point(centroid.y, centroid.x, year, timeout=timeout)
        if record:
            result.records.append(record)
        else:
            result.warnings.append(f"No CDL data for year {year}")

    return result


def summarize_crop_history(result: CDLHistoryResult) -> dict[str, Any]:
    """Summarize crop history into rotation analysis.

    Returns crop frequency counts, rotation pattern, and dominant crop.
    """
    if not result.records:
        return {"years": 0, "crops": {}, "rotation": []}

    crop_counts: dict[str, int] = {}
    rotation: list[dict[str, Any]] = []

    for rec in sorted(result.records, key=lambda r: r.year):
        crop_counts[rec.crop_name] = crop_counts.get(rec.crop_name, 0) + 1
        rotation.append(
            {
                "year": rec.year,
                "crop": rec.crop_name,
                "code": rec.crop_code,
            }
        )

    dominant = max(crop_counts, key=crop_counts.get) if crop_counts else None

    return {
        "years": len(result.records),
        "crops": crop_counts,
        "rotation": rotation,
        "dominant_crop": dominant,
        "centroid": {
            "lat": result.centroid_lat,
            "lon": result.centroid_lon,
        },
    }


def _parse_cropscape_value(response_text: str) -> int | None:
    """Parse crop code from CropScape API response text."""
    # CropScape returns XML like:
    # <GetCDLValueResponse>
    #   <Result>value=1,category=Corn,color=FFD300</Result>
    # </GetCDLValueResponse>
    # Or sometimes just text like "Result: {'value': '1', ...}"
    import re

    # Try XML parse
    if "<Result>" in response_text:
        match = re.search(r"value=(\d+)", response_text)
        if match:
            return int(match.group(1))

    # Try JSON-like parse
    match = re.search(r"['\"]value['\"]:\s*['\"]?(\d+)", response_text)
    if match:
        return int(match.group(1))

    return None
