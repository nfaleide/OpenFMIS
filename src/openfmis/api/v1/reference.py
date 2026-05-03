"""Reference data endpoints -- crop types, FCIC codes, tillage types, units."""

from typing import Annotated

from fastapi import APIRouter, Depends

from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.data_validation import (
    VALID_CROP_CODES,
    VALID_TILLAGE_TYPES,
    VALID_UNITS,
)

router = APIRouter(prefix="/reference", tags=["reference"])

# USDA NASS crop codes — code → name
CROP_CODE_NAMES: dict[int, str] = {
    1: "Corn",
    2: "Cotton",
    4: "Sorghum",
    5: "Soybeans",
    6: "Sunflower",
    21: "Barley",
    22: "Durum Wheat",
    23: "Spring Wheat",
    24: "Winter Wheat",
    27: "Rye",
    28: "Oats",
    29: "Millet",
    31: "Canola",
    36: "Alfalfa",
    37: "Other Hay/Non-Alfalfa",
    41: "Sugarbeets",
    42: "Dry Beans",
    43: "Potatoes",
    53: "Peas",
    61: "Fallow/Idle Cropland",
    176: "Grass/Pasture",
}

# FCIC crop codes (subset commonly used for insurance)
FCIC_CROP_CODES: dict[int, str] = {
    41: "Corn",
    81: "Soybeans",
    11: "Wheat",
    44: "Grain Sorghum",
    51: "Cotton",
    91: "Sunflowers",
    56: "Barley",
    75: "Oats",
    31: "Canola",
    17: "Dry Beans",
    84: "Sugar Beets",
    36: "Alfalfa Seed",
    47: "Potatoes",
    71: "Rye",
}


@router.get("/crop-types", summary="List crop types")
async def list_crop_types(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Return all USDA NASS crop codes with names."""
    return [
        {"code": code, "name": CROP_CODE_NAMES.get(code, f"Code {code}")}
        for code in sorted(VALID_CROP_CODES)
    ]


@router.get("/fcic-crops", summary="List fcic crops")
async def list_fcic_crops(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[dict]:
    """Return FCIC crop codes used for insurance."""
    return [{"code": code, "name": name} for code, name in sorted(FCIC_CROP_CODES.items())]


@router.get("/tillage-types", summary="List tillage types")
async def list_tillage_types(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """Return valid tillage type identifiers."""
    return sorted(VALID_TILLAGE_TYPES)


@router.get("/units", summary="List units")
async def list_units(
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[str]:
    """Return valid ADAPT unit abbreviations."""
    return sorted(VALID_UNITS)
