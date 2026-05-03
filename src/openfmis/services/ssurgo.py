"""SSURGO soil survey data service.

Queries the USDA Soil Data Access (SDA) service to retrieve soil
properties for field boundaries.  Uses the SDA REST API which
accepts SQL queries against the SSURGO database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
from shapely.geometry import shape as shapely_shape

log = logging.getLogger(__name__)

# USDA Soil Data Access REST endpoint — no API key required
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"


@dataclass
class SoilComponent:
    """A soil map unit component with properties."""

    mukey: str
    musym: str
    muname: str
    compname: str
    comppct: int  # Component percentage
    slope_low: float | None = None
    slope_high: float | None = None
    taxclname: str | None = None  # Taxonomic class
    drainagecl: str | None = None
    hydgrp: str | None = None  # Hydrologic group (A, B, C, D)
    om_low: float | None = None  # Organic matter % (low)
    om_high: float | None = None  # Organic matter % (high)
    cec_low: float | None = None
    cec_high: float | None = None
    ph_low: float | None = None
    ph_high: float | None = None
    ksat_low: float | None = None  # Saturated hydraulic conductivity
    ksat_high: float | None = None
    aws_025: float | None = None  # Available water storage 0-25cm
    aws_050: float | None = None  # Available water storage 0-50cm
    aws_100: float | None = None  # Available water storage 0-100cm


@dataclass
class SSURGOResult:
    """SSURGO query result for a field boundary."""

    components: list[SoilComponent] = field(default_factory=list)
    dominant_component: str | None = None
    dominant_drainage: str | None = None
    dominant_hydgrp: str | None = None
    warnings: list[str] = field(default_factory=list)


async def query_sda(sql: str, timeout: float = 30.0) -> dict[str, Any] | None:
    """Execute a SQL query against SDA and return the JSON response.

    Returns None if the query fails.
    """
    payload = {"query": sql, "format": "JSON"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(SDA_URL, json=payload)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        log.warning("SDA query failed: %s", exc)
        return None


async def get_soil_properties(
    geometry_geojson: dict[str, Any],
    timeout: float = 30.0,
) -> SSURGOResult:
    """Get SSURGO soil properties for a field boundary.

    Queries SDA for map units intersecting the field polygon, then
    retrieves component-level soil properties.

    Args:
        geometry_geojson: GeoJSON geometry (Polygon or MultiPolygon).
        timeout: HTTP timeout.

    Returns:
        SSURGOResult with soil components and dominant properties.
    """
    result = SSURGOResult()

    geom = shapely_shape(geometry_geojson)
    wkt = geom.wkt

    # Step 1: Get map unit keys (mukeys) intersecting the geometry
    mukey_sql = f"""
        SELECT M.mukey, M.musym, M.muname
        FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}') AS I
        INNER JOIN mapunit AS M ON M.mukey = I.mukey
    """

    mukey_data = await query_sda(mukey_sql, timeout=timeout)
    if not mukey_data or "Table" not in mukey_data:
        result.warnings.append("No SSURGO map units found for this geometry")
        return result

    mukeys = []
    mukey_info: dict[str, dict[str, str]] = {}
    for row in mukey_data["Table"]:
        mk = str(row[0])
        mukeys.append(mk)
        mukey_info[mk] = {"musym": str(row[1]), "muname": str(row[2])}

    if not mukeys:
        result.warnings.append("No SSURGO map units found")
        return result

    # Step 2: Get component properties
    mukey_list = ",".join(f"'{m}'" for m in mukeys)
    comp_sql = f"""
        SELECT
            c.mukey, c.compname, c.comppct_r,
            c.slope_l, c.slope_h,
            c.taxclname, c.drainagecl, c.hydgrp
        FROM component AS c
        WHERE c.mukey IN ({mukey_list})
        AND c.comppct_r IS NOT NULL
        ORDER BY c.comppct_r DESC
    """

    comp_data = await query_sda(comp_sql, timeout=timeout)
    if comp_data and "Table" in comp_data:
        for row in comp_data["Table"]:
            mk = str(row[0])
            info = mukey_info.get(mk, {"musym": "", "muname": ""})
            comp = SoilComponent(
                mukey=mk,
                musym=info["musym"],
                muname=info["muname"],
                compname=str(row[1]) if row[1] else "",
                comppct=int(row[2]) if row[2] else 0,
                slope_low=_float_or_none(row[3]),
                slope_high=_float_or_none(row[4]),
                taxclname=str(row[5]) if row[5] else None,
                drainagecl=str(row[6]) if row[6] else None,
                hydgrp=str(row[7]) if row[7] else None,
            )
            result.components.append(comp)

    # Step 3: Get horizon-level properties for dominant components
    if mukeys:
        horizon_sql = f"""
            SELECT
                c.mukey, c.compname,
                AVG(h.om_l) AS om_l, AVG(h.om_h) AS om_h,
                AVG(h.cec7_l) AS cec_l, AVG(h.cec7_h) AS cec_h,
                AVG(h.ph1to1h2o_l) AS ph_l, AVG(h.ph1to1h2o_h) AS ph_h,
                AVG(h.ksat_l) AS ksat_l, AVG(h.ksat_h) AS ksat_h
            FROM component AS c
            INNER JOIN chorizon AS h ON h.cokey = c.cokey
            WHERE c.mukey IN ({mukey_list})
            AND h.hzdept_r < 30
            GROUP BY c.mukey, c.compname
        """
        hz_data = await query_sda(horizon_sql, timeout=timeout)
        if hz_data and "Table" in hz_data:
            hz_lookup: dict[tuple[str, str], dict] = {}
            for row in hz_data["Table"]:
                key = (str(row[0]), str(row[1]))
                hz_lookup[key] = {
                    "om_low": _float_or_none(row[2]),
                    "om_high": _float_or_none(row[3]),
                    "cec_low": _float_or_none(row[4]),
                    "cec_high": _float_or_none(row[5]),
                    "ph_low": _float_or_none(row[6]),
                    "ph_high": _float_or_none(row[7]),
                    "ksat_low": _float_or_none(row[8]),
                    "ksat_high": _float_or_none(row[9]),
                }
            for comp in result.components:
                key = (comp.mukey, comp.compname)
                if key in hz_lookup:
                    props = hz_lookup[key]
                    comp.om_low = props["om_low"]
                    comp.om_high = props["om_high"]
                    comp.cec_low = props["cec_low"]
                    comp.cec_high = props["cec_high"]
                    comp.ph_low = props["ph_low"]
                    comp.ph_high = props["ph_high"]
                    comp.ksat_low = props["ksat_low"]
                    comp.ksat_high = props["ksat_high"]

    # Determine dominant properties
    if result.components:
        dominant = max(result.components, key=lambda c: c.comppct)
        result.dominant_component = dominant.compname
        result.dominant_drainage = dominant.drainagecl
        result.dominant_hydgrp = dominant.hydgrp

    return result


def summarize_soil(result: SSURGOResult) -> dict[str, Any]:
    """Summarize SSURGO data into a concise field soil profile."""
    if not result.components:
        return {"components": 0}

    total_pct = sum(c.comppct for c in result.components)

    # Weighted average of properties
    def _wavg(attr: str) -> float | None:
        vals = []
        for c in result.components:
            low = getattr(c, f"{attr}_low", None)
            high = getattr(c, f"{attr}_high", None)
            if low is not None and high is not None:
                vals.append(((low + high) / 2, c.comppct))
            elif low is not None:
                vals.append((low, c.comppct))
        if not vals:
            return None
        w_sum = sum(v * w for v, w in vals)
        w_total = sum(w for _, w in vals)
        return round(w_sum / w_total, 2) if w_total > 0 else None

    return {
        "components": len(result.components),
        "dominant_component": result.dominant_component,
        "dominant_drainage": result.dominant_drainage,
        "dominant_hydgrp": result.dominant_hydgrp,
        "weighted_om_pct": _wavg("om"),
        "weighted_cec": _wavg("cec"),
        "weighted_ph": _wavg("ph"),
        "total_mapped_pct": total_pct,
        "soil_names": list({c.compname for c in result.components}),
    }


def _float_or_none(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
