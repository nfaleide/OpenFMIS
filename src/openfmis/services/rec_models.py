"""University nutrient recommendation models — IL, IA, IN/OH, MN.

Implements standard Corn Belt extension service nutrient recommendation
frameworks for nitrogen (N), phosphorus (P), and potassium (K).

Supported models:
  - **MRTN** (IL/IA) — Maximum Return to Nitrogen.  Economic optimum N
    rate based on corn/N price ratio and previous crop.
  - **Tri-State** (IN/OH/MI) — Soil-test-based P & K recommendations
    with critical level + buildup/maintenance approach.
  - **UMN** (MN) — University of Minnesota N guidelines with previous-
    crop credits and soil organic matter adjustments.

All rates returned in **lbs/acre**.  Soil test values expected in **ppm**.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common types
# ---------------------------------------------------------------------------


class Nutrient(StrEnum):
    N = "N"
    P2O5 = "P2O5"
    K2O = "K2O"


class PreviousCrop(StrEnum):
    CORN = "corn"
    SOYBEAN = "soybean"
    ALFALFA = "alfalfa"
    SMALL_GRAIN = "small_grain"
    OTHER = "other"


class SoilTexture(StrEnum):
    SAND = "sand"
    LOAM = "loam"
    CLAY = "clay"
    SILT_LOAM = "silt_loam"
    CLAY_LOAM = "clay_loam"


@dataclass
class NutrientRecommendation:
    """Single nutrient recommendation result."""

    nutrient: Nutrient
    rate_lbs_ac: float
    model: str
    notes: str = ""


@dataclass
class RecInput:
    """Common input for recommendation models."""

    crop: str = "corn"
    yield_goal: float = 200.0  # bu/ac
    previous_crop: PreviousCrop = PreviousCrop.SOYBEAN
    soil_test_p_ppm: float | None = None  # Bray P1 or Mehlich-3
    soil_test_k_ppm: float | None = None  # exchangeable K
    soil_om_pct: float | None = None  # organic matter %
    soil_texture: SoilTexture = SoilTexture.LOAM
    corn_price: float = 5.50  # $/bu
    n_price: float = 0.50  # $/lb N
    cec: float | None = None  # cation exchange capacity


# ---------------------------------------------------------------------------
# MRTN — Maximum Return to Nitrogen (Illinois / Iowa)
# ---------------------------------------------------------------------------

# MRTN regional parameters: (base_rate, price_ratio_coeff)
# Derived from Nafziger (IL) and Sawyer (IA) MRTN databases.
# Base rate at 1:1 price ratio, coefficient adjusts for price ratio.
_MRTN_PARAMS = {
    # (previous_crop, state): (base_rate_at_1to1, price_sensitivity)
    ("corn", "IL"): (200, -28),
    ("soybean", "IL"): (175, -28),
    ("corn", "IA"): (195, -26),
    ("soybean", "IA"): (170, -26),
}


def mrtn_nitrogen(
    previous_crop: PreviousCrop,
    corn_price: float = 5.50,
    n_price: float = 0.50,
    state: str = "IL",
) -> NutrientRecommendation:
    """Calculate MRTN economic optimum nitrogen rate.

    The MRTN approach finds the N rate that maximizes return to N,
    accounting for the corn/N price ratio.  Higher price ratios
    (cheap N relative to corn) favor higher N rates.

    Args:
        previous_crop: Previous crop in rotation.
        corn_price: Corn grain price ($/bu).
        n_price: Nitrogen price ($/lb N).
        state: "IL" or "IA" for regional parameters.

    Returns:
        NutrientRecommendation with N rate in lbs/ac.
    """
    state = state.upper()
    if state not in ("IL", "IA"):
        raise ValueError(f"MRTN model supports IL and IA, got '{state}'")

    prev = "soybean" if previous_crop == PreviousCrop.SOYBEAN else "corn"
    key = (prev, state)
    base_rate, sensitivity = _MRTN_PARAMS.get(key, (185, -27))

    # Price ratio: $/lb N / $/bu corn
    if corn_price <= 0:
        raise ValueError("corn_price must be positive")
    price_ratio = n_price / corn_price

    # MRTN rate = base + sensitivity * ln(price_ratio)
    # At ratio ~0.1 (cheap N): high rate; at ratio ~0.15: moderate
    import math

    rate = base_rate + sensitivity * math.log(max(price_ratio, 0.01))

    # Clamp to agronomic bounds
    rate = max(50, min(rate, 250))

    return NutrientRecommendation(
        nutrient=Nutrient.N,
        rate_lbs_ac=round(rate, 1),
        model=f"MRTN-{state}",
        notes=f"Previous crop: {previous_crop.value}, price ratio: {price_ratio:.3f}",
    )


# ---------------------------------------------------------------------------
# Tri-State (Indiana / Ohio / Michigan) — P & K
# ---------------------------------------------------------------------------

# Critical soil test levels (ppm) and maintenance rates (lbs/bu removed)
# Source: Tri-State Fertilizer Recommendations (Vitosh, Johnson, Mengel)
_TRISTATE_P = {
    # soil_test_critical_ppm, buildup_factor, maintenance_per_bu
    "corn": (20, 1.5, 0.37),  # 0.37 lb P2O5 per bu corn
    "soybean": (20, 1.5, 0.80),
}

_TRISTATE_K = {
    # For CEC categories: low (<12), medium (12-20), high (>20)
    "corn": {
        "critical": {"low": 100, "medium": 120, "high": 130},
        "maintenance_per_bu": 0.27,
        "buildup_factor": 4.0,
    },
    "soybean": {
        "critical": {"low": 100, "medium": 120, "high": 130},
        "maintenance_per_bu": 1.40,
        "buildup_factor": 4.0,
    },
}


def tristate_phosphorus(
    soil_test_p_ppm: float,
    crop: str = "corn",
    yield_goal: float = 200.0,
) -> NutrientRecommendation:
    """Tri-State P2O5 recommendation.

    Below the critical level: buildup + maintenance.
    At/above critical: maintenance only.
    Well above critical: no P recommended.

    Args:
        soil_test_p_ppm: Bray P1 or Mehlich-3 P (ppm).
        crop: "corn" or "soybean".
        yield_goal: Expected yield (bu/ac).

    Returns:
        NutrientRecommendation with P2O5 rate.
    """
    crop = crop.lower()
    if crop not in _TRISTATE_P:
        raise ValueError(f"Tri-State P model supports corn/soybean, got '{crop}'")

    critical, buildup_factor, maint_per_bu = _TRISTATE_P[crop]
    maintenance = maint_per_bu * yield_goal

    if soil_test_p_ppm >= critical * 2:
        rate = 0.0
        notes = "Soil test well above critical — no P needed"
    elif soil_test_p_ppm >= critical:
        rate = maintenance
        notes = "At/above critical — maintenance only"
    else:
        deficit = critical - soil_test_p_ppm
        buildup = deficit * buildup_factor
        rate = buildup + maintenance
        notes = f"Below critical ({soil_test_p_ppm} vs {critical} ppm) — buildup + maintenance"

    return NutrientRecommendation(
        nutrient=Nutrient.P2O5,
        rate_lbs_ac=round(max(rate, 0), 1),
        model="Tri-State",
        notes=notes,
    )


def tristate_potassium(
    soil_test_k_ppm: float,
    crop: str = "corn",
    yield_goal: float = 200.0,
    cec: float | None = None,
) -> NutrientRecommendation:
    """Tri-State K2O recommendation.

    Uses CEC to determine the critical soil test K level.
    Below critical: buildup + maintenance.  Above: maintenance only.

    Args:
        soil_test_k_ppm: Exchangeable K (ppm).
        crop: "corn" or "soybean".
        yield_goal: Expected yield (bu/ac).
        cec: Cation exchange capacity. If None, uses medium (12-20) category.

    Returns:
        NutrientRecommendation with K2O rate.
    """
    crop = crop.lower()
    if crop not in _TRISTATE_K:
        raise ValueError(f"Tri-State K model supports corn/soybean, got '{crop}'")

    params = _TRISTATE_K[crop]

    # Determine CEC category
    if cec is not None:
        if cec < 12:
            cec_cat = "low"
        elif cec > 20:
            cec_cat = "high"
        else:
            cec_cat = "medium"
    else:
        cec_cat = "medium"

    critical = params["critical"][cec_cat]
    maintenance = params["maintenance_per_bu"] * yield_goal
    buildup_factor = params["buildup_factor"]

    if soil_test_k_ppm >= critical * 1.5:
        rate = 0.0
        notes = f"Soil test well above critical ({cec_cat} CEC) — no K needed"
    elif soil_test_k_ppm >= critical:
        rate = maintenance
        notes = f"At/above critical ({critical} ppm, {cec_cat} CEC) — maintenance only"
    else:
        deficit = critical - soil_test_k_ppm
        buildup = deficit * buildup_factor
        rate = buildup + maintenance
        notes = f"Below critical ({soil_test_k_ppm} vs {critical} ppm, {cec_cat} CEC)"

    return NutrientRecommendation(
        nutrient=Nutrient.K2O,
        rate_lbs_ac=round(max(rate, 0), 1),
        model="Tri-State",
        notes=notes,
    )


# ---------------------------------------------------------------------------
# UMN — University of Minnesota N guidelines
# ---------------------------------------------------------------------------

# Previous crop N credits (lbs/ac)
_UMN_N_CREDITS = {
    PreviousCrop.SOYBEAN: 40,
    PreviousCrop.ALFALFA: 150,  # Good stand, 3+ cuts
    PreviousCrop.SMALL_GRAIN: 0,
    PreviousCrop.CORN: 0,
    PreviousCrop.OTHER: 0,
}

# Organic matter N credit: lbs N per % OM above 3%
_UMN_OM_CREDIT_PER_PCT = 15


def umn_nitrogen(
    yield_goal: float = 200.0,
    previous_crop: PreviousCrop = PreviousCrop.SOYBEAN,
    soil_om_pct: float | None = None,
    soil_texture: SoilTexture = SoilTexture.LOAM,
) -> NutrientRecommendation:
    """University of Minnesota corn nitrogen recommendation.

    Uses yield goal, previous crop credits, and soil OM adjustments.
    N rate = (yield_goal * factor) - previous_crop_credit - OM_credit.

    Args:
        yield_goal: Expected corn yield (bu/ac).
        previous_crop: Previous crop in rotation.
        soil_om_pct: Soil organic matter %. If None, no OM credit applied.
        soil_texture: Soil texture class (affects base factor).

    Returns:
        NutrientRecommendation with N rate in lbs/ac.
    """
    # Base N factor: lbs N per bu yield goal
    # Fine textures need less N (more mineralization), sandy soils need more
    texture_factors = {
        SoilTexture.SAND: 1.2,
        SoilTexture.LOAM: 1.0,
        SoilTexture.SILT_LOAM: 1.0,
        SoilTexture.CLAY_LOAM: 0.95,
        SoilTexture.CLAY: 0.90,
    }
    factor = texture_factors.get(soil_texture, 1.0)

    base_n = yield_goal * factor

    # Previous crop credit
    prev_credit = _UMN_N_CREDITS.get(previous_crop, 0)

    # OM credit (above 3%)
    om_credit = 0.0
    if soil_om_pct is not None and soil_om_pct > 3.0:
        om_credit = (soil_om_pct - 3.0) * _UMN_OM_CREDIT_PER_PCT

    rate = base_n - prev_credit - om_credit
    rate = max(0, min(rate, 250))

    notes_parts = [f"Yield goal: {yield_goal} bu/ac"]
    if prev_credit > 0:
        notes_parts.append(f"{previous_crop.value} credit: -{prev_credit} lbs")
    if om_credit > 0:
        notes_parts.append(f"OM credit ({soil_om_pct}%): -{om_credit:.0f} lbs")

    return NutrientRecommendation(
        nutrient=Nutrient.N,
        rate_lbs_ac=round(rate, 1),
        model="UMN",
        notes="; ".join(notes_parts),
    )


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------


def recommend(
    model: str,
    nutrient: str,
    inputs: RecInput,
) -> NutrientRecommendation:
    """Unified recommendation dispatch.

    Args:
        model: Model name — "mrtn-il", "mrtn-ia", "tri-state", "umn".
        nutrient: Nutrient — "N", "P2O5", "K2O".
        inputs: Common input parameters.

    Returns:
        NutrientRecommendation.

    Raises:
        ValueError: If model/nutrient combination is unsupported.
    """
    model_lower = model.lower()
    nutrient_upper = nutrient.upper()

    if model_lower.startswith("mrtn"):
        if nutrient_upper != "N":
            raise ValueError("MRTN model only supports N recommendations")
        state = model_lower.split("-")[1].upper() if "-" in model_lower else "IL"
        return mrtn_nitrogen(
            previous_crop=inputs.previous_crop,
            corn_price=inputs.corn_price,
            n_price=inputs.n_price,
            state=state,
        )

    elif model_lower == "tri-state":
        if nutrient_upper == "P2O5":
            if inputs.soil_test_p_ppm is None:
                raise ValueError("soil_test_p_ppm required for Tri-State P")
            return tristate_phosphorus(
                soil_test_p_ppm=inputs.soil_test_p_ppm,
                crop=inputs.crop,
                yield_goal=inputs.yield_goal,
            )
        elif nutrient_upper == "K2O":
            if inputs.soil_test_k_ppm is None:
                raise ValueError("soil_test_k_ppm required for Tri-State K")
            return tristate_potassium(
                soil_test_k_ppm=inputs.soil_test_k_ppm,
                crop=inputs.crop,
                yield_goal=inputs.yield_goal,
                cec=inputs.cec,
            )
        else:
            raise ValueError("Tri-State model supports P2O5 and K2O")

    elif model_lower == "umn":
        if nutrient_upper != "N":
            raise ValueError("UMN model only supports N recommendations")
        return umn_nitrogen(
            yield_goal=inputs.yield_goal,
            previous_crop=inputs.previous_crop,
            soil_om_pct=inputs.soil_om_pct,
            soil_texture=inputs.soil_texture,
        )

    else:
        raise ValueError(f"Unknown model '{model}'. Supported: mrtn-il, mrtn-ia, tri-state, umn")
