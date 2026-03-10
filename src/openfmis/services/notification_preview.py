"""NotificationPreviewService — generate thumbnail previews for scene notifications.

Produces: true color, false color infrared, and analyzed index composites.
Stores as PNG files in the upload directory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import SceneRecord
from openfmis.services.scene_notification import SceneNotification

log = logging.getLogger(__name__)

PREVIEW_SIZE = 256  # thumbnail pixel size


class NotificationPreviewService:
    def __init__(self, db: AsyncSession, storage_path: str | None = None) -> None:
        self.db = db
        self.storage_path = storage_path or os.environ.get("UPLOAD_STORAGE_PATH", "/data/uploads")

    async def generate_previews(
        self,
        notification_id: uuid.UUID,
        scene_id: str,
        field_geojson: dict,
        index_type: str | None = None,
    ) -> dict[str, str]:
        """Generate true-color, false-color IR, and index preview thumbnails.

        Returns dict of {preview_type: file_path}.
        """
        # Get scene assets
        result = await self.db.execute(select(SceneRecord).where(SceneRecord.scene_id == scene_id))
        scene = result.scalar_one_or_none()
        if scene is None:
            log.warning("Cannot generate previews: scene %s not found", scene_id)
            return {}

        assets = scene.assets or {}
        preview_dir = os.path.join(self.storage_path, "previews", str(notification_id))
        os.makedirs(preview_dir, exist_ok=True)

        previews = {}

        # True color (R, G, B)
        try:
            tc_path = os.path.join(preview_dir, "true_color.png")
            await asyncio.to_thread(
                _render_rgb_thumbnail,
                assets,
                field_geojson,
                ["red", "green", "blue"],
                tc_path,
                scene.collection,
            )
            previews["true_color"] = tc_path
        except Exception as exc:
            log.warning("True color preview failed: %s", exc)

        # False color IR (NIR, R, G)
        try:
            fc_path = os.path.join(preview_dir, "false_color.png")
            await asyncio.to_thread(
                _render_rgb_thumbnail,
                assets,
                field_geojson,
                ["nir", "red", "green"],
                fc_path,
                scene.collection,
            )
            previews["false_color"] = fc_path
        except Exception as exc:
            log.warning("False color preview failed: %s", exc)

        # Straight NIR
        try:
            nir_path = os.path.join(preview_dir, "nir.png")
            await asyncio.to_thread(
                _render_single_band_thumbnail,
                assets,
                field_geojson,
                "nir",
                nir_path,
                scene.collection,
            )
            previews["nir"] = nir_path
        except Exception as exc:
            log.warning("NIR preview failed: %s", exc)

        # Index layer (if an analysis job exists)
        if index_type:
            try:
                idx_path = os.path.join(preview_dir, f"{index_type}.png")
                await asyncio.to_thread(
                    _render_index_thumbnail,
                    assets,
                    field_geojson,
                    index_type,
                    idx_path,
                    scene.collection,
                )
                previews["index_layer"] = idx_path
            except Exception as exc:
                log.warning("Index preview failed: %s", exc)

        # Update notification with preview URLs
        notif_result = await self.db.execute(
            select(SceneNotification).where(SceneNotification.id == notification_id)
        )
        notif = notif_result.scalar_one_or_none()
        if notif:
            notif.metadata_ = {**(notif.metadata_ or {}), "preview_urls": previews}
            await self.db.flush()

        return previews


def _render_rgb_thumbnail(
    assets: dict,
    geojson: dict,
    band_keys: list[str],
    output_path: str,
    collection: str,
) -> None:
    """Read 3 bands, normalize, composite to RGB PNG thumbnail."""
    from PIL import Image

    from openfmis.services.band_registry import get_profile
    from openfmis.services.image_extraction import _read_band_sync

    try:
        profile = get_profile(collection)
    except KeyError:
        from openfmis.services.band_registry import SENTINEL2_L2A

        profile = SENTINEL2_L2A

    bands = []
    for key in band_keys:
        if key not in assets:
            raise ValueError(f"Band {key} not in assets")
        arr = _read_band_sync(
            assets[key],
            geojson,
            scale_factor=profile.scale_factor,
            scale_offset=profile.scale_offset,
            nodata_value=profile.nodata_value,
        )
        bands.append(arr)

    # Stack and normalize to 0-255
    rgb = np.stack(bands, axis=-1)
    rgb = np.nan_to_num(rgb, nan=0.0)
    # Percentile stretch for visualization
    for i in range(3):
        band = rgb[:, :, i]
        valid = band[band > 0]
        if valid.size > 0:
            p2, p98 = np.percentile(valid, [2, 98])
            band = np.clip((band - p2) / (p98 - p2 + 1e-10), 0, 1)
            rgb[:, :, i] = band

    rgb_uint8 = (rgb * 255).astype(np.uint8)
    img = Image.fromarray(rgb_uint8)
    img = img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
    img.save(output_path, "PNG")


def _render_single_band_thumbnail(
    assets: dict,
    geojson: dict,
    band_key: str,
    output_path: str,
    collection: str,
) -> None:
    """Render a single band as a grayscale thumbnail."""
    from PIL import Image

    from openfmis.services.band_registry import get_profile
    from openfmis.services.image_extraction import _read_band_sync

    try:
        profile = get_profile(collection)
    except KeyError:
        from openfmis.services.band_registry import SENTINEL2_L2A

        profile = SENTINEL2_L2A

    if band_key not in assets:
        raise ValueError(f"Band {band_key} not in assets")

    arr = _read_band_sync(
        assets[band_key],
        geojson,
        scale_factor=profile.scale_factor,
        scale_offset=profile.scale_offset,
        nodata_value=profile.nodata_value,
    )
    arr = np.nan_to_num(arr, nan=0.0)
    valid = arr[arr > 0]
    if valid.size > 0:
        p2, p98 = np.percentile(valid, [2, 98])
        arr = np.clip((arr - p2) / (p98 - p2 + 1e-10), 0, 1)

    gray = (arr * 255).astype(np.uint8)
    img = Image.fromarray(gray, mode="L")
    img = img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
    img.save(output_path, "PNG")


def _render_index_thumbnail(
    assets: dict,
    geojson: dict,
    index_type: str,
    output_path: str,
    collection: str,
) -> None:
    """Compute an index and render as a colorized thumbnail (RdYlGn colormap)."""
    from PIL import Image

    from openfmis.services.band_math import BUILTIN_INDICES, evaluate, extract_required_bands
    from openfmis.services.band_registry import get_profile
    from openfmis.services.image_extraction import _read_band_sync

    # Find formula
    formula = None
    parameters = None
    for idx in BUILTIN_INDICES:
        if idx["slug"] == index_type:
            formula = idx["formula"]
            parameters = idx.get("parameters")
            break
    if formula is None:
        raise ValueError(f"Unknown index: {index_type}")

    try:
        profile = get_profile(collection)
    except KeyError:
        from openfmis.services.band_registry import SENTINEL2_L2A

        profile = SENTINEL2_L2A

    required = extract_required_bands(formula)
    band_arrays = {}
    for key in required:
        if key not in assets:
            raise ValueError(f"Band {key} not in assets")
        band_arrays[key] = _read_band_sync(
            assets[key],
            geojson,
            scale_factor=profile.scale_factor,
            scale_offset=profile.scale_offset,
            nodata_value=profile.nodata_value,
        )

    index_arr = evaluate(formula, band_arrays, parameters)
    index_arr = np.nan_to_num(index_arr, nan=0.0)

    # RdYlGn colormap: red (low) → yellow (mid) → green (high)
    # Normalize to 0-1 range (most indices are -1 to 1)
    normalized = np.clip((index_arr + 1) / 2, 0, 1)

    # Simple 3-stop gradient: red → yellow → green
    r = np.where(normalized < 0.5, 1.0, 1.0 - 2 * (normalized - 0.5))
    g = np.where(normalized < 0.5, 2 * normalized, 1.0)
    b = np.full_like(normalized, 0.1)

    rgb = np.stack([r, g, b], axis=-1)
    rgb_uint8 = (rgb * 255).astype(np.uint8)
    img = Image.fromarray(rgb_uint8)
    img = img.resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
    img.save(output_path, "PNG")
