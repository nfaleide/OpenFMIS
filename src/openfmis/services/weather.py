"""Weather and Growing Degree Day (GDD) service.

Provides temperature-based GDD accumulation and basic weather data
retrieval.  Uses Open-Meteo API (free, no API key) for historical
and forecast weather data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

log = logging.getLogger(__name__)

# Open-Meteo API — free, no API key
OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"

# GDD base temperatures (°F)
GDD_BASE_CORN = 50.0
GDD_BASE_SOYBEANS = 50.0
GDD_BASE_WHEAT = 32.0

# Upper cutoff for modified GDD (corn)
GDD_UPPER_CORN = 86.0


@dataclass
class DailyWeather:
    """Daily weather observation."""

    date: date
    temp_max_f: float
    temp_min_f: float
    precip_in: float
    gdd: float = 0.0


@dataclass
class WeatherResult:
    """Weather data for a location over a date range."""

    daily: list[DailyWeather] = field(default_factory=list)
    cumulative_gdd: float = 0.0
    total_precip_in: float = 0.0
    avg_temp_f: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class GDDResult:
    """GDD accumulation result."""

    total_gdd: float
    daily_gdd: list[tuple[date, float]]
    base_temp_f: float
    upper_temp_f: float | None
    start_date: date
    end_date: date


def calculate_gdd(
    temp_max_f: float,
    temp_min_f: float,
    base_f: float = GDD_BASE_CORN,
    upper_f: float | None = GDD_UPPER_CORN,
) -> float:
    """Calculate Growing Degree Days for a single day.

    Uses the modified GDD method:
    1. Cap max temp at upper limit (if set)
    2. Cap min temp at base temp
    3. GDD = ((capped_max + capped_min) / 2) - base
    4. If negative, GDD = 0

    Args:
        temp_max_f: Maximum temperature (°F).
        temp_min_f: Minimum temperature (°F).
        base_f: Base temperature (°F).
        upper_f: Upper cutoff (°F). None for simple method.

    Returns:
        GDD units for the day.
    """
    tmax = temp_max_f
    tmin = temp_min_f

    if upper_f is not None:
        tmax = min(tmax, upper_f)

    tmin = max(tmin, base_f)
    tmax = max(tmax, base_f)

    gdd = ((tmax + tmin) / 2.0) - base_f
    return max(0.0, gdd)


def accumulate_gdd(
    daily_temps: list[tuple[date, float, float]],
    base_f: float = GDD_BASE_CORN,
    upper_f: float | None = GDD_UPPER_CORN,
) -> GDDResult:
    """Accumulate GDD over a series of daily temperatures.

    Args:
        daily_temps: List of (date, max_temp_f, min_temp_f) tuples.
        base_f: Base temperature.
        upper_f: Upper cutoff.

    Returns:
        GDDResult with total and daily breakdown.
    """
    daily_gdd: list[tuple[date, float]] = []
    total = 0.0

    for d, tmax, tmin in daily_temps:
        gdd = calculate_gdd(tmax, tmin, base_f, upper_f)
        daily_gdd.append((d, gdd))
        total += gdd

    start = daily_temps[0][0] if daily_temps else date.today()
    end = daily_temps[-1][0] if daily_temps else date.today()

    return GDDResult(
        total_gdd=round(total, 1),
        daily_gdd=daily_gdd,
        base_temp_f=base_f,
        upper_temp_f=upper_f,
        start_date=start,
        end_date=end,
    )


def _c_to_f(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32.0


def _mm_to_in(mm: float) -> float:
    """Convert millimeters to inches."""
    return mm / 25.4


async def get_weather(
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    base_f: float = GDD_BASE_CORN,
    upper_f: float | None = GDD_UPPER_CORN,
    timeout: float = 15.0,
) -> WeatherResult:
    """Fetch historical weather data from Open-Meteo.

    Args:
        lat: Latitude (decimal degrees).
        lon: Longitude (decimal degrees).
        start_date: Start of range.
        end_date: End of range (inclusive).
        base_f: GDD base temperature (°F).
        upper_f: GDD upper cutoff (°F).
        timeout: HTTP timeout.

    Returns:
        WeatherResult with daily observations and GDD accumulation.
    """
    result = WeatherResult()

    # Use historical API for dates before yesterday
    yesterday = date.today() - timedelta(days=1)
    use_historical = end_date <= yesterday

    url = OPEN_METEO_HISTORICAL if use_historical else OPEN_METEO_FORECAST
    params: dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "timezone": "America/Chicago",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        result.warnings.append(f"Weather API error: {exc}")
        return result

    daily_data = data.get("daily", {})
    dates = daily_data.get("time", [])
    tmax_c = daily_data.get("temperature_2m_max", [])
    tmin_c = daily_data.get("temperature_2m_min", [])
    precip_mm = daily_data.get("precipitation_sum", [])

    cumulative_gdd = 0.0
    total_precip = 0.0
    temp_sum = 0.0

    for i, d_str in enumerate(dates):
        d = date.fromisoformat(d_str)
        tmax_f = _c_to_f(tmax_c[i]) if tmax_c[i] is not None else 50.0
        tmin_f = _c_to_f(tmin_c[i]) if tmin_c[i] is not None else 40.0
        precip_in = _mm_to_in(precip_mm[i]) if precip_mm[i] is not None else 0.0

        gdd = calculate_gdd(tmax_f, tmin_f, base_f, upper_f)
        cumulative_gdd += gdd
        total_precip += precip_in
        temp_sum += (tmax_f + tmin_f) / 2.0

        result.daily.append(
            DailyWeather(
                date=d,
                temp_max_f=round(tmax_f, 1),
                temp_min_f=round(tmin_f, 1),
                precip_in=round(precip_in, 2),
                gdd=round(gdd, 1),
            )
        )

    result.cumulative_gdd = round(cumulative_gdd, 1)
    result.total_precip_in = round(total_precip, 2)
    if result.daily:
        result.avg_temp_f = round(temp_sum / len(result.daily), 1)

    return result


def summarize_weather(result: WeatherResult) -> dict[str, Any]:
    """Summarize weather data into a concise report."""
    if not result.daily:
        return {"days": 0}

    return {
        "days": len(result.daily),
        "cumulative_gdd": result.cumulative_gdd,
        "total_precip_in": result.total_precip_in,
        "avg_temp_f": result.avg_temp_f,
        "max_temp_f": max(d.temp_max_f for d in result.daily),
        "min_temp_f": min(d.temp_min_f for d in result.daily),
        "max_daily_precip_in": max(d.precip_in for d in result.daily),
        "rainy_days": sum(1 for d in result.daily if d.precip_in > 0.01),
    }
