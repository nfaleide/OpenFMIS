"""Reporting & analytics engine.

Generates field-level and group-level agronomic reports from stored
data: soil tests, crop history, yield analysis, nutrient trends,
prescription cost/ROI, and as-applied vs prescription comparison.

Reports produce structured dicts that can be rendered to HTML/PDF
(via the existing pdf_report service) or exported as Excel/CSV.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────


@dataclass
class SoilTestSummary:
    """Summary of soil test results for a field."""

    field_name: str
    crop_year: int
    samples: int = 0
    analytes: dict[str, dict[str, float]] = field(default_factory=dict)
    # Each analyte: {"min": x, "max": x, "mean": x, "median": x, "unit": "ppm"}


@dataclass
class YieldAnalysisResult:
    """Yield analysis by category (hybrid, tillage, soil type)."""

    field_name: str
    crop_year: int
    crop: str | None = None
    overall_mean: float = 0.0
    overall_std: float = 0.0
    by_category: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # e.g. {"hybrid": [{"name": "DKC62-08", "mean": 195, "std": 10, "n": 500}]}


@dataclass
class NutrientTrendPoint:
    """A single point in a nutrient trend over years."""

    year: int
    value: float
    unit: str


@dataclass
class PrescriptionCostResult:
    """Cost/ROI analysis for a prescription."""

    rx_name: str
    product: str
    total_acres: float
    total_product: float
    product_unit: str
    cost_per_unit: float
    total_cost: float
    avg_rate: float
    min_rate: float
    max_rate: float
    zones: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AsAppliedComparison:
    """Comparison of as-applied vs prescription rates."""

    field_name: str
    product: str
    zones: list[dict[str, Any]] = field(default_factory=list)
    overall_accuracy_pct: float = 0.0
    total_over_applied: float = 0.0
    total_under_applied: float = 0.0


# ── Report generators ──────────────────────────────────────────────────


def soil_test_summary(
    field_name: str,
    crop_year: int,
    test_data: list[dict[str, Any]],
) -> SoilTestSummary:
    """Generate soil test summary from raw test data.

    Args:
        field_name: Name of the field.
        crop_year: Crop year.
        test_data: List of dicts, each with analyte values.
            e.g. [{"p_ppm": 15, "k_ppm": 150, "ph": 6.5, "om_pct": 3.2}, ...]

    Returns:
        SoilTestSummary with per-analyte statistics.
    """
    result = SoilTestSummary(
        field_name=field_name,
        crop_year=crop_year,
        samples=len(test_data),
    )

    if not test_data:
        return result

    # Collect all analyte keys
    all_keys: set[str] = set()
    for row in test_data:
        all_keys.update(row.keys())

    units = {
        "p_ppm": "ppm",
        "k_ppm": "ppm",
        "ph": "",
        "om_pct": "%",
        "cec": "meq/100g",
        "no3": "ppm",
        "so4": "ppm",
        "zn": "ppm",
        "mn": "ppm",
        "fe": "ppm",
        "cu": "ppm",
        "ca": "ppm",
        "mg": "ppm",
        "na": "ppm",
        "b": "ppm",
    }

    for key in sorted(all_keys):
        vals = []
        for row in test_data:
            v = row.get(key)
            if v is not None:
                try:
                    vals.append(float(v))
                except (ValueError, TypeError):
                    pass
        if vals:
            arr = np.array(vals)
            result.analytes[key] = {
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "mean": round(float(np.mean(arr)), 2),
                "median": round(float(np.median(arr)), 2),
                "std": round(float(np.std(arr)), 2),
                "n": len(vals),
                "unit": units.get(key, ""),
            }

    return result


def yield_analysis(
    field_name: str,
    crop_year: int,
    points: list[dict[str, Any]],
    crop: str | None = None,
    group_by: list[str] | None = None,
) -> YieldAnalysisResult:
    """Analyze yield data by grouping categories.

    Args:
        field_name: Name of the field.
        crop_year: Crop year.
        points: List of dicts with at least "yield" key and optional
            grouping columns (hybrid, tillage, soil_type).
        crop: Crop name.
        group_by: Columns to group by. Defaults to ["hybrid"].

    Returns:
        YieldAnalysisResult with overall and per-group statistics.
    """
    if group_by is None:
        group_by = ["hybrid"]

    result = YieldAnalysisResult(
        field_name=field_name,
        crop_year=crop_year,
        crop=crop,
    )

    # Overall stats
    yields = [float(p["yield"]) for p in points if "yield" in p and p["yield"] is not None]
    if yields:
        arr = np.array(yields)
        result.overall_mean = round(float(np.mean(arr)), 2)
        result.overall_std = round(float(np.std(arr)), 2)

    # Group-by analysis
    for col in group_by:
        groups: dict[str, list[float]] = {}
        for p in points:
            key = str(p.get(col, "Unknown"))
            val = p.get("yield")
            if val is not None:
                try:
                    groups.setdefault(key, []).append(float(val))
                except (ValueError, TypeError):
                    pass

        group_stats = []
        for name, vals in sorted(groups.items()):
            arr = np.array(vals)
            group_stats.append(
                {
                    "name": name,
                    "mean": round(float(np.mean(arr)), 2),
                    "std": round(float(np.std(arr)), 2),
                    "min": round(float(np.min(arr)), 2),
                    "max": round(float(np.max(arr)), 2),
                    "n": len(vals),
                }
            )
        result.by_category[col] = group_stats

    return result


def nutrient_trends(
    analyte: str,
    unit: str,
    yearly_data: list[tuple[int, list[float]]],
) -> list[NutrientTrendPoint]:
    """Compute nutrient trend over multiple years.

    Args:
        analyte: Analyte name (e.g. "p_ppm").
        unit: Unit string (e.g. "ppm").
        yearly_data: List of (year, [values]) tuples.

    Returns:
        List of NutrientTrendPoint with yearly means.
    """
    points = []
    for year, vals in sorted(yearly_data, key=lambda x: x[0]):
        if vals:
            mean_val = round(float(np.mean(vals)), 2)
            points.append(NutrientTrendPoint(year=year, value=mean_val, unit=unit))
    return points


def prescription_cost(
    rx_name: str,
    product: str,
    product_unit: str,
    cost_per_unit: float,
    zones: list[dict[str, Any]],
) -> PrescriptionCostResult:
    """Calculate prescription cost and ROI metrics.

    Args:
        rx_name: Prescription name.
        product: Product name.
        product_unit: Unit (e.g. "lbs", "gal").
        cost_per_unit: Cost per unit of product.
        zones: List of dicts with "acres", "rate" keys.

    Returns:
        PrescriptionCostResult with total cost breakdown.
    """
    total_acres = 0.0
    total_product = 0.0
    rates = []
    zone_details = []

    for z in zones:
        acres = float(z.get("acres", 0))
        rate = float(z.get("rate", 0))
        product_amount = acres * rate
        zone_cost = product_amount * cost_per_unit

        total_acres += acres
        total_product += product_amount
        rates.append(rate)
        zone_details.append(
            {
                "zone": z.get("label", z.get("zone_id", "")),
                "acres": round(acres, 2),
                "rate": round(rate, 2),
                "product_amount": round(product_amount, 2),
                "cost": round(zone_cost, 2),
            }
        )

    return PrescriptionCostResult(
        rx_name=rx_name,
        product=product,
        total_acres=round(total_acres, 2),
        total_product=round(total_product, 2),
        product_unit=product_unit,
        cost_per_unit=cost_per_unit,
        total_cost=round(total_product * cost_per_unit, 2),
        avg_rate=round(float(np.mean(rates)), 2) if rates else 0.0,
        min_rate=round(min(rates), 2) if rates else 0.0,
        max_rate=round(max(rates), 2) if rates else 0.0,
        zones=zone_details,
    )


def as_applied_comparison(
    field_name: str,
    product: str,
    rx_zones: list[dict[str, Any]],
    applied_zones: list[dict[str, Any]],
) -> AsAppliedComparison:
    """Compare as-applied rates against prescription rates.

    Args:
        field_name: Field name.
        product: Product name.
        rx_zones: List of rx dicts with "zone_id", "rate", "acres".
        applied_zones: List of applied dicts with "zone_id", "rate".

    Returns:
        AsAppliedComparison with per-zone accuracy.
    """
    result = AsAppliedComparison(field_name=field_name, product=product)

    applied_map = {str(z["zone_id"]): float(z["rate"]) for z in applied_zones}

    total_rx = 0.0
    total_applied = 0.0
    zone_comparisons = []

    for rx in rx_zones:
        zone_id = str(rx["zone_id"])
        rx_rate = float(rx["rate"])
        acres = float(rx.get("acres", 0))
        applied_rate = applied_map.get(zone_id)

        if applied_rate is not None:
            diff = applied_rate - rx_rate
            pct = (diff / rx_rate * 100) if rx_rate != 0 else 0.0
            total_rx += rx_rate * acres
            total_applied += applied_rate * acres

            if diff > 0:
                result.total_over_applied += diff * acres
            else:
                result.total_under_applied += abs(diff) * acres

            zone_comparisons.append(
                {
                    "zone_id": zone_id,
                    "rx_rate": round(rx_rate, 2),
                    "applied_rate": round(applied_rate, 2),
                    "diff": round(diff, 2),
                    "diff_pct": round(pct, 1),
                    "acres": round(acres, 2),
                }
            )

    result.zones = zone_comparisons
    if total_rx > 0:
        result.overall_accuracy_pct = round((1 - abs(total_applied - total_rx) / total_rx) * 100, 1)
    result.total_over_applied = round(result.total_over_applied, 2)
    result.total_under_applied = round(result.total_under_applied, 2)

    return result


# ── Export to CSV ───────────────────────────────────────────────────────


def soil_test_to_csv(summary: SoilTestSummary) -> bytes:
    """Export soil test summary as CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Field", summary.field_name])
    writer.writerow(["Crop Year", summary.crop_year])
    writer.writerow(["Samples", summary.samples])
    writer.writerow([])
    writer.writerow(["Analyte", "Unit", "Min", "Max", "Mean", "Median", "Std", "N"])

    for analyte, stats in sorted(summary.analytes.items()):
        writer.writerow(
            [
                analyte,
                stats.get("unit", ""),
                stats["min"],
                stats["max"],
                stats["mean"],
                stats["median"],
                stats["std"],
                stats["n"],
            ]
        )

    return buf.getvalue().encode("utf-8")


def yield_analysis_to_csv(result: YieldAnalysisResult) -> bytes:
    """Export yield analysis as CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Field", result.field_name])
    writer.writerow(["Crop Year", result.crop_year])
    writer.writerow(["Crop", result.crop or ""])
    writer.writerow(["Overall Mean", result.overall_mean])
    writer.writerow(["Overall Std", result.overall_std])
    writer.writerow([])

    for category, groups in result.by_category.items():
        writer.writerow([f"By {category}"])
        writer.writerow(["Name", "Mean", "Std", "Min", "Max", "N"])
        for g in groups:
            writer.writerow(
                [
                    g["name"],
                    g["mean"],
                    g["std"],
                    g["min"],
                    g["max"],
                    g["n"],
                ]
            )
        writer.writerow([])

    return buf.getvalue().encode("utf-8")


def prescription_cost_to_csv(result: PrescriptionCostResult) -> bytes:
    """Export prescription cost analysis as CSV bytes."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["Prescription", result.rx_name])
    writer.writerow(["Product", result.product])
    writer.writerow(["Total Acres", result.total_acres])
    writer.writerow(["Total Product", result.total_product, result.product_unit])
    writer.writerow(["Cost/Unit", result.cost_per_unit])
    writer.writerow(["Total Cost", result.total_cost])
    writer.writerow([])
    writer.writerow(["Zone", "Acres", "Rate", "Product Amount", "Cost"])

    for z in result.zones:
        writer.writerow(
            [
                z["zone"],
                z["acres"],
                z["rate"],
                z["product_amount"],
                z["cost"],
            ]
        )

    return buf.getvalue().encode("utf-8")
