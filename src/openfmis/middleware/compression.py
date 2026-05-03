"""GZip compression middleware for large responses.

Particularly important for geospatial endpoints (MVT tiles,
GeoJSON exports, large JSON list responses).
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.gzip import GZipMiddleware


def add_gzip_middleware(app: FastAPI, minimum_size: int = 1000) -> None:
    """Add GZip compression for responses larger than *minimum_size* bytes."""
    app.add_middleware(GZipMiddleware, minimum_size=minimum_size)
