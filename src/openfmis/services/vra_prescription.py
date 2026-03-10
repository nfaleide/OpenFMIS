"""VRAPrescriptionService — generate variable-rate application prescriptions.

Supports TGT (target), FODM (flat-rate on-demand), and BMP (bitmap spreadmap) formats.
Prescription zones are derived from analysis job results + classification breakpoints.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import AnalysisJob

log = logging.getLogger(__name__)


class JobNotReadyError(Exception):
    pass


class VRAPrescriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_tgt(
        self,
        job_id: uuid.UUID,
        zones: list[dict],
    ) -> dict:
        """Generate a TGT (target rate) prescription from analysis zones.

        Each zone dict: {zone_name, min_value, max_value, target_rate, unit}
        Returns a prescription dict ready for export.
        """
        job = await self._get_completed_job(job_id)
        _validate_zones(zones)

        prescription_zones = []
        for z in zones:
            prescription_zones.append(
                {
                    "zone_name": z["zone_name"],
                    "min_value": z["min_value"],
                    "max_value": z["max_value"],
                    "target_rate": z["target_rate"],
                    "unit": z.get("unit", "lbs/ac"),
                }
            )

        return {
            "type": "tgt",
            "job_id": str(job.id),
            "field_id": str(job.field_id),
            "scene_id": job.scene_id,
            "index_type": job.index_type,
            "zones": prescription_zones,
        }

    async def generate_fodm(
        self,
        job_id: uuid.UUID,
        base_rate: float,
        rate_adjustment: float,
        num_zones: int = 5,
        unit: str = "lbs/ac",
    ) -> dict:
        """Generate a FODM (flat on-demand) prescription.

        Evenly divides the index range into num_zones, applying
        linear rate adjustment from base_rate.
        """
        job = await self._get_completed_job(job_id)
        result = job.result or {}
        idx_min = result.get("min", 0.0)
        idx_max = result.get("max", 1.0)

        step = (idx_max - idx_min) / num_zones
        zones = []
        for i in range(num_zones):
            zone_min = idx_min + i * step
            zone_max = idx_min + (i + 1) * step
            zone_mid = (zone_min + zone_max) / 2
            # Linear interpolation: low index = high rate, high index = low rate
            rate = base_rate + rate_adjustment * (1.0 - (zone_mid - idx_min) / (idx_max - idx_min))
            zones.append(
                {
                    "zone_name": f"Zone {i + 1}",
                    "min_value": round(zone_min, 4),
                    "max_value": round(zone_max, 4),
                    "target_rate": round(rate, 2),
                    "unit": unit,
                }
            )

        return {
            "type": "fodm",
            "job_id": str(job.id),
            "field_id": str(job.field_id),
            "scene_id": job.scene_id,
            "index_type": job.index_type,
            "base_rate": base_rate,
            "rate_adjustment": rate_adjustment,
            "zones": zones,
        }

    async def generate_bmp(
        self,
        job_id: uuid.UUID,
        breakpoints: list[float],
        rates: list[float],
        unit: str = "lbs/ac",
    ) -> dict:
        """Generate a BMP (bitmap spreadmap) prescription.

        breakpoints: sorted list of N-1 values dividing N zones
        rates: list of N rates, one per zone
        """
        job = await self._get_completed_job(job_id)

        if len(rates) != len(breakpoints) + 1:
            raise ValueError(
                f"rates length ({len(rates)}) must be "
                f"breakpoints length + 1 ({len(breakpoints) + 1})"
            )

        result = job.result or {}
        idx_min = result.get("min", 0.0)
        idx_max = result.get("max", 1.0)

        boundaries = [idx_min] + breakpoints + [idx_max]
        zones = []
        for i in range(len(rates)):
            zones.append(
                {
                    "zone_name": f"Zone {i + 1}",
                    "min_value": round(boundaries[i], 4),
                    "max_value": round(boundaries[i + 1], 4),
                    "target_rate": rates[i],
                    "unit": unit,
                }
            )

        return {
            "type": "bmp",
            "job_id": str(job.id),
            "field_id": str(job.field_id),
            "scene_id": job.scene_id,
            "index_type": job.index_type,
            "zones": zones,
        }

    async def configure_zones(
        self,
        job_id: uuid.UUID,
        zone_configs: list[dict],
    ) -> dict:
        """Store custom zone configuration for a job's prescription."""
        job = await self._get_completed_job(job_id)
        return {
            "job_id": str(job.id),
            "field_id": str(job.field_id),
            "zone_configs": zone_configs,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _get_completed_job(self, job_id: uuid.UUID) -> AnalysisJob:
        result = await self.db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        if job.status != "complete":
            raise JobNotReadyError(
                f"Job {job_id} is {job.status}, must be complete to generate prescription"
            )
        return job


def _validate_zones(zones: list[dict]) -> None:
    for z in zones:
        if "zone_name" not in z or "target_rate" not in z:
            raise ValueError("Each zone must have zone_name and target_rate")
        if "min_value" not in z or "max_value" not in z:
            raise ValueError("Each zone must have min_value and max_value")
