"""Data validation service — plausible range checks for point data."""

from typing import Any

from openfmis.schemas.point_ingestion import ValidationIssue

# ── Plausible ranges ────────────────────────────────────────────────────────

SOIL_RANGES: dict[str, tuple[float, float]] = {
    "ph": (3.0, 10.0),
    "om_pct": (0.0, 30.0),
    "p_ppm": (0.0, 500.0),
    "k_ppm": (0.0, 2000.0),
    "cec": (0.0, 100.0),
    "no3": (0.0, 500.0),
    "so4": (0.0, 500.0),
    "zn": (0.0, 100.0),
    "mn": (0.0, 200.0),
    "fe": (0.0, 500.0),
    "cu": (0.0, 50.0),
    "ca": (0.0, 10000.0),
    "mg": (0.0, 5000.0),
    "na": (0.0, 5000.0),
    "b": (0.0, 20.0),
}

YIELD_RANGES: dict[str, tuple[float, float]] = {
    "bu/ac": (0.0, 500.0),
    "bu_ac": (0.0, 500.0),
    "lbs/ac": (0.0, 30000.0),
    "lb/ac": (0.0, 30000.0),
    "moisture": (0.0, 50.0),
}

APPLIED_RANGES: dict[str, tuple[float, float]] = {
    "fert_rate": (0.0, 1000.0),
    "chem_rate": (0.0, 200.0),
}

EC_RANGE = (0.0, 200.0)

# ── USDA NASS crop codes ───────────────────────────────────────────────────

VALID_CROP_CODES = {
    1,
    2,
    4,
    5,
    6,
    21,
    22,
    23,
    24,
    27,
    28,
    29,
    31,
    36,
    37,
    41,
    42,
    43,
    53,
    61,
    176,
}

# ── ADAPT unit abbreviations ──────────────────────────────────────────────

VALID_UNITS = {
    "bu",
    "bu/ac",
    "lb",
    "lb/ac",
    "gal",
    "gal/ac",
    "oz",
    "oz/ac",
    "pt",
    "pt/ac",
    "qt",
    "qt/ac",
    "ton",
    "ton/ac",
    "kg",
    "kg/ha",
    "L",
    "L/ha",
    "ppm",
    "meq/100g",
    "%",
    "mS/m",
    "dS/m",
    "seeds/ac",
    "seeds/ft",
    "in",
    "mm",
    "cm",
}

VALID_TILLAGE_TYPES = {
    "no_till",
    "strip_till",
    "min_till",
    "chisel",
    "disk",
    "moldboard",
    "vertical",
    "unknown",
}


def validate_rows(
    dataset_type: str,
    values: list[dict[str, Any]],
    unit: str | None = None,
    check_coordinates: bool = True,
    conus_only: bool = False,
) -> list[ValidationIssue]:
    """Validate a list of row dicts, returning issues found."""
    issues: list[ValidationIssue] = []

    for i, row in enumerate(values):
        # Coordinate checks
        if check_coordinates:
            lat = _to_float(row.get("lat") or row.get("latitude") or row.get("y"))
            lon = _to_float(row.get("lon") or row.get("longitude") or row.get("x"))
            if lat is not None and (lat < -90 or lat > 90):
                issues.append(
                    ValidationIssue(
                        row=i, column="lat", value=lat, issue="Latitude out of range [-90, 90]"
                    )
                )
            if lon is not None and (lon < -180 or lon > 180):
                issues.append(
                    ValidationIssue(
                        row=i, column="lon", value=lon, issue="Longitude out of range [-180, 180]"
                    )
                )
            if conus_only and lat is not None and lon is not None:
                if not (24 <= lat <= 50 and -125 <= lon <= -66):
                    issues.append(
                        ValidationIssue(
                            row=i,
                            column="coords",
                            value=f"{lat},{lon}",
                            issue="Outside CONUS bounds",
                        )
                    )

        # Value range checks
        if dataset_type == "soil_test":
            issues.extend(_check_soil_ranges(i, row))
        elif dataset_type == "yield":
            issues.extend(_check_yield_ranges(i, row, unit))
        elif dataset_type in ("as_applied_fert", "as_applied_chem"):
            issues.extend(_check_applied_ranges(i, row, dataset_type))
        elif dataset_type == "ec_em":
            issues.extend(_check_ec_ranges(i, row))

    return issues


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _check_soil_ranges(row_idx: int, row: dict) -> list[ValidationIssue]:
    issues = []
    for col, (lo, hi) in SOIL_RANGES.items():
        val = _to_float(row.get(col))
        if val is not None and (val < lo or val > hi):
            issues.append(
                ValidationIssue(
                    row=row_idx,
                    column=col,
                    value=val,
                    issue=f"Value {val} outside plausible range [{lo}, {hi}]",
                )
            )
    return issues


def _check_yield_ranges(row_idx: int, row: dict, unit: str | None) -> list[ValidationIssue]:
    issues = []
    range_key = unit if unit in YIELD_RANGES else "bu/ac"
    lo, hi = YIELD_RANGES.get(range_key, (0.0, 500.0))
    for col in ("yield", "yld_vol_dr", "yld_mass_d", "dry_yield", "wet_yield", "bu_ac"):
        val = _to_float(row.get(col))
        if val is not None and (val < lo or val > hi):
            issues.append(
                ValidationIssue(
                    row=row_idx,
                    column=col,
                    value=val,
                    issue=f"Value {val} outside plausible range [{lo}, {hi}]",
                )
            )
    return issues


def _check_applied_ranges(row_idx: int, row: dict, dtype: str) -> list[ValidationIssue]:
    issues = []
    range_key = "fert_rate" if dtype == "as_applied_fert" else "chem_rate"
    lo, hi = APPLIED_RANGES[range_key]
    for col in (
        "rate",
        "rt_apd_ct",
        "rt_apd_ms",
        "applied_rate",
        "app_rate",
        "product_ra",
        "rate_actual",
    ):
        val = _to_float(row.get(col))
        if val is not None and (val < lo or val > hi):
            issues.append(
                ValidationIssue(
                    row=row_idx,
                    column=col,
                    value=val,
                    issue=f"Value {val} outside plausible range [{lo}, {hi}]",
                )
            )
    return issues


def _check_ec_ranges(row_idx: int, row: dict) -> list[ValidationIssue]:
    issues = []
    lo, hi = EC_RANGE
    for col in ("ec_0_12", "ec_12_24", "ec_shallow", "ec_deep", "em_h", "em_v"):
        val = _to_float(row.get(col))
        if val is not None and (val < lo or val > hi):
            issues.append(
                ValidationIssue(
                    row=row_idx,
                    column=col,
                    value=val,
                    issue=f"Value {val} outside plausible range [{lo}, {hi}]",
                )
            )
    return issues
