"""CustomImageryService — handle user-uploaded GeoTIFF imagery.

Upload flow: save file → background process (read metadata) → create synthetic SceneRecord.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.custom_scene import CustomScene
from openfmis.models.satshot import SceneRecord

log = logging.getLogger(__name__)

DEFAULT_UPLOAD_PATH = "/data/uploads"


class CustomImageryService:
    def __init__(self, db: AsyncSession, upload_path: str | None = None) -> None:
        self.db = db
        self.upload_path = upload_path or os.environ.get("UPLOAD_STORAGE_PATH", DEFAULT_UPLOAD_PATH)

    async def upload(
        self,
        file_bytes: bytes,
        filename: str,
        group_id: uuid.UUID,
        uploaded_by: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        band_names: list[str] | None = None,
        acquired_at: datetime | None = None,
    ) -> CustomScene:
        """Save uploaded file and create a CustomScene record.

        Processing (metadata extraction) runs in the background.
        """
        # Save file
        scene_uuid = uuid.uuid4()
        ext = Path(filename).suffix or ".tif"
        dest_dir = os.path.join(self.upload_path, str(group_id))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, f"{scene_uuid}{ext}")

        await asyncio.to_thread(_write_file, dest_path, file_bytes)

        record = CustomScene(
            id=scene_uuid,
            group_id=group_id,
            uploaded_by=uploaded_by,
            name=name or filename,
            description=description,
            file_path=dest_path,
            file_size_bytes=len(file_bytes),
            band_names=band_names,
            acquired_at=acquired_at,
            status="processing",
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)

        # Fire background processing
        asyncio.create_task(self._process_upload(record.id))
        return record

    async def _process_upload(self, scene_id: uuid.UUID) -> None:
        """Background: extract raster metadata and create synthetic SceneRecord."""
        from openfmis.database import async_session_factory

        async with async_session_factory() as db:
            try:
                result = await db.execute(select(CustomScene).where(CustomScene.id == scene_id))
                scene = result.scalar_one_or_none()
                if scene is None:
                    return

                meta = await asyncio.to_thread(_extract_raster_metadata, scene.file_path)

                scene.crs = meta["crs"]
                scene.band_count = meta["band_count"]
                scene.bounds = meta["bounds"]
                scene.pixel_resolution_m = meta.get("resolution_m")
                scene.band_metadata = meta.get("band_metadata")

                if not scene.band_names and meta.get("band_descriptions"):
                    scene.band_names = meta["band_descriptions"]

                # Create footprint from bounds
                b = meta["bounds"]  # [left, bottom, right, top]
                if b:
                    scene.footprint = (
                        f"SRID=4326;MULTIPOLYGON((("
                        f"{b[0]} {b[1]}, {b[2]} {b[1]}, {b[2]} {b[3]}, {b[0]} {b[3]}, {b[0]} {b[1]}"
                        f")))"
                    )

                # Build assets dict mapping band names to file paths
                assets = {}
                names = scene.band_names or [f"band_{i + 1}" for i in range(meta["band_count"])]
                for i, bname in enumerate(names):
                    assets[bname] = f"{scene.file_path}#{i + 1}"

                # Create synthetic SceneRecord for unified pipeline
                synth_scene_id = f"custom-{scene.id}"
                synth = SceneRecord(
                    scene_id=synth_scene_id,
                    collection="custom-upload",
                    acquired_at=scene.acquired_at or datetime.now(UTC),
                    cloud_cover=None,
                    bbox=meta["bounds"],
                    assets=assets,
                    stac_properties={"source": "upload", "filename": scene.name},
                    footprint=scene.footprint,
                )
                db.add(synth)
                await db.flush()

                scene.scene_record_id = synth.id
                scene.status = "ready"
                await db.commit()
                log.info(
                    "Custom scene %s processed: %d bands, CRS=%s",
                    scene_id,
                    meta["band_count"],
                    meta["crs"],
                )

            except Exception as exc:
                log.exception("Failed to process custom scene %s: %s", scene_id, exc)
                try:
                    result = await db.execute(select(CustomScene).where(CustomScene.id == scene_id))
                    scene = result.scalar_one_or_none()
                    if scene:
                        scene.status = "failed"
                        await db.commit()
                except Exception:
                    pass

    async def list_scenes(
        self, group_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> list[CustomScene]:
        result = await self.db.execute(
            select(CustomScene)
            .where(CustomScene.group_id == group_id)
            .order_by(CustomScene.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_scene(self, scene_id: uuid.UUID) -> CustomScene | None:
        result = await self.db.execute(select(CustomScene).where(CustomScene.id == scene_id))
        return result.scalar_one_or_none()

    async def delete_scene(self, scene_id: uuid.UUID) -> None:
        scene = await self.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"Custom scene not found: {scene_id}")

        # Delete file
        if scene.file_path and os.path.exists(scene.file_path):
            await asyncio.to_thread(os.remove, scene.file_path)

        # Delete synthetic scene record
        if scene.scene_record_id:
            synth = await self.db.execute(
                select(SceneRecord).where(SceneRecord.id == scene.scene_record_id)
            )
            synth_record = synth.scalar_one_or_none()
            if synth_record:
                await self.db.delete(synth_record)

        await self.db.delete(scene)
        await self.db.flush()


def _write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _extract_raster_metadata(file_path: str) -> dict[str, Any]:
    """Read GeoTIFF metadata with rasterio (synchronous)."""
    import rasterio

    with rasterio.open(file_path) as src:
        bounds = list(src.bounds)
        res = src.res  # (x_res, y_res) in CRS units

        band_metadata = []
        band_descriptions = []
        for i in range(1, src.count + 1):
            desc = src.descriptions[i - 1] if src.descriptions else None
            band_descriptions.append(desc or f"band_{i}")
            band_metadata.append(
                {
                    "index": i,
                    "dtype": str(src.dtypes[i - 1]),
                    "nodata": src.nodata,
                    "description": desc,
                }
            )

        return {
            "crs": str(src.crs) if src.crs else None,
            "band_count": src.count,
            "bounds": bounds,
            "resolution_m": float(res[0]) if res else None,
            "band_metadata": band_metadata,
            "band_descriptions": band_descriptions,
        }
