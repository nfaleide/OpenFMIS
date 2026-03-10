"""ImageryExportService — export analysis results as GeoTIFF, shapefile, GeoJSON, KML."""

from __future__ import annotations

import io
import logging
import os
import tempfile
import uuid
import zipfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import AnalysisJob

log = logging.getLogger(__name__)


class ImageryExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def export_geojson(
        self,
        job_id: uuid.UUID,
        zones: list[dict] | None = None,
    ) -> dict:
        """Export analysis result as a GeoJSON FeatureCollection.

        If zones are provided, each zone becomes a Feature with properties.
        Otherwise returns the job result as feature properties on the field geometry.
        """
        job = await self._get_job(job_id)
        features = []

        if zones:
            for z in zones:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {
                            "zone_name": z.get("zone_name"),
                            "min_value": z.get("min_value"),
                            "max_value": z.get("max_value"),
                            "target_rate": z.get("target_rate"),
                            "index_type": job.index_type,
                        },
                        "geometry": z.get("geometry"),
                    }
                )
        else:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "job_id": str(job.id),
                        "field_id": str(job.field_id),
                        "scene_id": job.scene_id,
                        "index_type": job.index_type,
                        **(job.result or {}),
                    },
                    "geometry": None,
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    async def export_csv(self, job_id: uuid.UUID, zones: list[dict] | None = None) -> str:
        """Export analysis/prescription zones as CSV text."""
        job = await self._get_job(job_id)
        lines = ["zone_name,min_value,max_value,target_rate,unit,index_type"]

        if zones:
            for z in zones:
                lines.append(
                    f"{z.get('zone_name', '')},{z.get('min_value', '')},{z.get('max_value', '')},"
                    f"{z.get('target_rate', '')},{z.get('unit', '')},{job.index_type}"
                )
        else:
            result = job.result or {}
            lines.append(
                f"full_field,{result.get('min', '')},{result.get('max', '')},"
                f",lbs/ac,{job.index_type}"
            )

        return "\n".join(lines)

    async def export_kml(self, job_id: uuid.UUID, zones: list[dict] | None = None) -> str:
        """Export analysis zones as KML."""
        job = await self._get_job(job_id)
        placemarks = []

        if zones:
            for z in zones:
                geom = z.get("geometry")
                coords_str = ""
                if geom and geom.get("type") == "Polygon":
                    ring = geom["coordinates"][0]
                    coords_str = " ".join(f"{lon},{lat},0" for lon, lat in ring)

                placemarks.append(
                    f"<Placemark>"
                    f"<name>{z.get('zone_name', '')}</name>"
                    f"<description>Rate: {z.get('target_rate', '')} "
                    f"{z.get('unit', '')}</description>"
                    f"<Polygon><outerBoundaryIs><LinearRing>"
                    f"<coordinates>{coords_str}</coordinates>"
                    f"</LinearRing></outerBoundaryIs></Polygon>"
                    f"</Placemark>"
                )

        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<kml xmlns="http://www.opengis.net/kml/2.2">'
            f"<Document><name>Analysis {job.index_type} - {job.scene_id}</name>"
            f"{''.join(placemarks)}"
            "</Document></kml>"
        )

    async def export_shapefile_bytes(self, job_id: uuid.UUID, zones: list[dict]) -> bytes:
        """Export zones as a zipped shapefile using fiona."""
        import fiona
        from fiona.crs import from_epsg

        job = await self._get_job(job_id)

        schema = {
            "geometry": "Polygon",
            "properties": {
                "zone_name": "str",
                "min_value": "float",
                "max_value": "float",
                "rate": "float",
                "unit": "str",
                "index": "str",
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, "prescription.shp")
            with fiona.open(
                shp_path, "w", driver="ESRI Shapefile", schema=schema, crs=from_epsg(4326)
            ) as dst:
                for z in zones:
                    dst.write(
                        {
                            "geometry": z.get("geometry"),
                            "properties": {
                                "zone_name": z.get("zone_name", ""),
                                "min_value": z.get("min_value", 0),
                                "max_value": z.get("max_value", 0),
                                "rate": z.get("target_rate", 0),
                                "unit": z.get("unit", ""),
                                "index": job.index_type,
                            },
                        }
                    )

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname in os.listdir(tmpdir):
                    zf.write(os.path.join(tmpdir, fname), fname)
            return buf.getvalue()

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _get_job(self, job_id: uuid.UUID) -> AnalysisJob:
        result = await self.db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job
