"""Drone imagery import service.

Handles upload and registration of drone-captured GeoTIFF imagery.
Extracts metadata (bounds, CRS, band count, resolution) and creates
a CoreDataset record linked to the field.  The imagery is stored
as a file reference (local path or object storage URL) and can be
served through the tile engine.
"""

from __future__ import annotations

import io
import logging
import os
import struct
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

log = logging.getLogger(__name__)


@dataclass
class DroneImageMetadata:
    """Metadata extracted from a drone GeoTIFF."""

    width: int = 0
    height: int = 0
    band_count: int = 0
    crs: str | None = None
    bounds: tuple[float, float, float, float] | None = None  # minx, miny, maxx, maxy
    resolution_x: float | None = None
    resolution_y: float | None = None
    nodata: float | None = None
    dtype: str | None = None
    file_size_bytes: int = 0
    capture_date: datetime | None = None


@dataclass
class DroneImportResult:
    """Result of drone imagery import."""

    success: bool
    dataset_id: UUID | None = None
    metadata: DroneImageMetadata | None = None
    storage_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def extract_geotiff_metadata(
    file_content: bytes,
) -> DroneImageMetadata:
    """Extract metadata from a GeoTIFF file using rasterio.

    Args:
        file_content: Raw GeoTIFF bytes.

    Returns:
        DroneImageMetadata with spatial and band information.
    """
    try:
        import rasterio
    except ImportError:
        log.warning("rasterio not available — using basic TIFF header parsing")
        return _basic_tiff_metadata(file_content)

    meta = DroneImageMetadata(file_size_bytes=len(file_content))

    try:
        src = rasterio.open(io.BytesIO(file_content))
    except Exception:
        log.warning("rasterio failed to open file — using basic TIFF header parsing")
        return _basic_tiff_metadata(file_content)

    with src:
        meta.width = src.width
        meta.height = src.height
        meta.band_count = src.count
        meta.crs = str(src.crs) if src.crs else None
        meta.bounds = tuple(src.bounds)
        if src.res:
            meta.resolution_x = src.res[0]
            meta.resolution_y = src.res[1]
        meta.nodata = src.nodata
        meta.dtype = str(src.dtypes[0]) if src.dtypes else None

        # Try to extract capture date from TIFF tags
        tags = src.tags()
        for key in ("TIFFTAG_DATETIME", "datetime", "acquisition_date"):
            if key in tags:
                try:
                    meta.capture_date = datetime.fromisoformat(tags[key])
                except (ValueError, TypeError):
                    pass
                break

    return meta


def _basic_tiff_metadata(file_content: bytes) -> DroneImageMetadata:
    """Fallback: extract basic info from TIFF header without rasterio."""
    meta = DroneImageMetadata(file_size_bytes=len(file_content))

    if len(file_content) < 8:
        return meta

    # Check TIFF magic bytes
    byte_order = file_content[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return meta

    magic = struct.unpack(f"{endian}H", file_content[2:4])[0]
    if magic != 42:
        return meta

    # Read IFD offset
    ifd_offset = struct.unpack(f"{endian}I", file_content[4:8])[0]
    if ifd_offset >= len(file_content):
        return meta

    # Read IFD entry count
    count = struct.unpack(f"{endian}H", file_content[ifd_offset : ifd_offset + 2])[0]

    for i in range(min(count, 100)):
        offset = ifd_offset + 2 + i * 12
        if offset + 12 > len(file_content):
            break

        tag = struct.unpack(f"{endian}H", file_content[offset : offset + 2])[0]
        value = struct.unpack(f"{endian}I", file_content[offset + 8 : offset + 12])[0]

        if tag == 256:  # ImageWidth
            meta.width = value
        elif tag == 257:  # ImageLength
            meta.height = value
        elif tag == 277:  # SamplesPerPixel
            meta.band_count = value

    return meta


def validate_drone_image(
    meta: DroneImageMetadata,
    max_size_mb: int = 500,
) -> list[str]:
    """Validate drone image metadata.

    Returns list of error messages (empty if valid).
    """
    errors = []

    if meta.file_size_bytes > max_size_mb * 1024 * 1024:
        errors.append(
            f"File too large: {meta.file_size_bytes / 1024 / 1024:.0f} MB "
            f"exceeds {max_size_mb} MB limit"
        )

    if meta.width == 0 or meta.height == 0:
        errors.append("Could not determine image dimensions")

    if meta.band_count == 0:
        errors.append("Could not determine band count")

    if meta.bounds is not None:
        minx, miny, maxx, maxy = meta.bounds
        if minx == maxx or miny == maxy:
            errors.append("Image has zero spatial extent")

    return errors


async def import_drone_image(
    file_content: bytes,
    filename: str,
    field_id: UUID,
    storage_dir: str = "/tmp/drone_imagery",
    label: str | None = None,
    capture_date: datetime | None = None,
) -> DroneImportResult:
    """Import a drone GeoTIFF image.

    Extracts metadata, validates, stores the file, and returns
    the result. Caller should create the CoreDataset record
    from the returned metadata.

    Args:
        file_content: Raw GeoTIFF bytes.
        filename: Original filename.
        field_id: Field this imagery belongs to.
        storage_dir: Directory to store the file.
        label: Optional label for the dataset.
        capture_date: Override capture date.

    Returns:
        DroneImportResult with metadata and storage path.
    """
    result = DroneImportResult(success=False)

    # Extract metadata
    try:
        meta = extract_geotiff_metadata(file_content)
    except Exception as exc:
        result.error = f"Failed to read image metadata: {exc}"
        return result
    result.metadata = meta

    if capture_date:
        meta.capture_date = capture_date

    # Validate
    errors = validate_drone_image(meta)
    if errors:
        result.error = "; ".join(errors)
        result.warnings = errors
        return result

    # Store file
    os.makedirs(storage_dir, exist_ok=True)
    file_id = uuid4()
    ext = os.path.splitext(filename)[1] or ".tif"
    stored_name = f"{field_id}_{file_id}{ext}"
    stored_path = os.path.join(storage_dir, stored_name)

    with open(stored_path, "wb") as f:
        f.write(file_content)

    result.success = True
    result.dataset_id = file_id
    result.storage_path = stored_path

    log.info(
        "Drone image imported: %s (%dx%d, %d bands, %.1f MB)",
        filename,
        meta.width,
        meta.height,
        meta.band_count,
        meta.file_size_bytes / 1024 / 1024,
    )

    return result
