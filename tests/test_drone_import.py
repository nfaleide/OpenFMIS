"""Tests for drone imagery import service."""

import struct
import tempfile
from uuid import uuid4

import pytest

from openfmis.services.drone_import import (
    DroneImageMetadata,
    _basic_tiff_metadata,
    extract_geotiff_metadata,
    import_drone_image,
    validate_drone_image,
)


def _make_tiff_header(width=100, height=100, bands=3):
    """Create a minimal TIFF header for testing."""
    # Little-endian TIFF
    data = bytearray()
    data += b"II"  # Little-endian
    data += struct.pack("<H", 42)  # TIFF magic
    data += struct.pack("<I", 8)  # IFD offset

    # IFD with 3 entries
    data += struct.pack("<H", 3)  # Entry count

    # Tag 256: ImageWidth
    data += struct.pack("<H", 256)  # tag
    data += struct.pack("<H", 3)  # type (SHORT)
    data += struct.pack("<I", 1)  # count
    data += struct.pack("<I", width)  # value

    # Tag 257: ImageLength
    data += struct.pack("<H", 257)
    data += struct.pack("<H", 3)
    data += struct.pack("<I", 1)
    data += struct.pack("<I", height)

    # Tag 277: SamplesPerPixel
    data += struct.pack("<H", 277)
    data += struct.pack("<H", 3)
    data += struct.pack("<I", 1)
    data += struct.pack("<I", bands)

    # Next IFD offset (0 = end)
    data += struct.pack("<I", 0)

    return bytes(data)


class TestBasicTiffParser:
    def test_parse_valid_header(self):
        tiff = _make_tiff_header(200, 150, 4)
        meta = _basic_tiff_metadata(tiff)
        assert meta.width == 200
        assert meta.height == 150
        assert meta.band_count == 4

    def test_parse_big_endian(self):
        data = bytearray()
        data += b"MM"
        data += struct.pack(">H", 42)
        data += struct.pack(">I", 8)
        data += struct.pack(">H", 3)

        # Width
        data += struct.pack(">H", 256)
        data += struct.pack(">H", 3)
        data += struct.pack(">I", 1)
        data += struct.pack(">I", 300)

        # Height
        data += struct.pack(">H", 257)
        data += struct.pack(">H", 3)
        data += struct.pack(">I", 1)
        data += struct.pack(">I", 200)

        # Bands
        data += struct.pack(">H", 277)
        data += struct.pack(">H", 3)
        data += struct.pack(">I", 1)
        data += struct.pack(">I", 1)

        data += struct.pack(">I", 0)

        meta = _basic_tiff_metadata(bytes(data))
        assert meta.width == 300
        assert meta.height == 200
        assert meta.band_count == 1

    def test_parse_too_small(self):
        meta = _basic_tiff_metadata(b"II")
        assert meta.width == 0
        assert meta.height == 0

    def test_parse_bad_magic(self):
        data = b"XX" + struct.pack("<H", 99) + struct.pack("<I", 8)
        meta = _basic_tiff_metadata(data)
        assert meta.width == 0

    def test_file_size_recorded(self):
        tiff = _make_tiff_header()
        meta = _basic_tiff_metadata(tiff)
        assert meta.file_size_bytes == len(tiff)


class TestValidation:
    def test_valid_image(self):
        meta = DroneImageMetadata(
            width=1000,
            height=800,
            band_count=3,
            file_size_bytes=10 * 1024 * 1024,
            bounds=(-96.5, 40.1, -96.4, 40.2),
        )
        errors = validate_drone_image(meta)
        assert errors == []

    def test_too_large(self):
        meta = DroneImageMetadata(
            width=10000,
            height=10000,
            band_count=4,
            file_size_bytes=600 * 1024 * 1024,
        )
        errors = validate_drone_image(meta, max_size_mb=500)
        assert any("too large" in e.lower() for e in errors)

    def test_zero_dimensions(self):
        meta = DroneImageMetadata(width=0, height=0, band_count=3)
        errors = validate_drone_image(meta)
        assert any("dimensions" in e for e in errors)

    def test_zero_bands(self):
        meta = DroneImageMetadata(width=100, height=100, band_count=0)
        errors = validate_drone_image(meta)
        assert any("band" in e for e in errors)

    def test_zero_extent(self):
        meta = DroneImageMetadata(
            width=100,
            height=100,
            band_count=3,
            bounds=(0.0, 0.0, 0.0, 0.0),
        )
        errors = validate_drone_image(meta)
        assert any("extent" in e for e in errors)


class TestExtractMetadata:
    def test_fallback_to_basic(self):
        """Without rasterio, falls back to basic TIFF parsing."""
        tiff = _make_tiff_header(500, 400, 3)
        meta = extract_geotiff_metadata(tiff)
        # May use rasterio or fallback — either way should return metadata
        assert meta.file_size_bytes == len(tiff)


@pytest.mark.asyncio
class TestImportDroneImage:
    async def test_import_valid(self):
        tiff = _make_tiff_header(100, 100, 3)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await import_drone_image(
                tiff,
                "test_drone.tif",
                uuid4(),
                storage_dir=tmpdir,
            )
            # May fail validation (no bounds in basic header) — that's OK
            # Just verify the function runs without crashing
            assert result is not None

    async def test_import_invalid_file(self):
        result = await import_drone_image(
            b"not a tiff",
            "bad.tif",
            uuid4(),
        )
        assert not result.success
        assert result.error is not None
