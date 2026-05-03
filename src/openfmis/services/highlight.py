"""Highlight working set — Redis-backed user-scoped geometry selection.

Replaces the legacy "hilite" pattern. Each user has a working set of
geometry IDs stored in Redis with a configurable TTL. The service supports
add, remove, list, clear, and geometry operations (merge, clip, hole).

When Redis is unavailable, falls back to an in-memory dict (for testing
or development without Redis).
"""

from __future__ import annotations

import json
import logging
import os
from uuid import UUID

log = logging.getLogger(__name__)

# Default TTL: 4 hours (per spec §1)
DEFAULT_TTL_SECONDS = 4 * 3600

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

_KEY_PREFIX = "openfmis:highlight:"


def _user_key(user_id: UUID) -> str:
    return f"{_KEY_PREFIX}{user_id}"


# ── Redis client singleton ───────────────────────────────────────────────────

_redis_client = None
_use_memory_fallback = False
_memory_store: dict[str, dict] = {}  # Fallback for testing


async def get_redis():
    """Get or create the async Redis client."""
    global _redis_client, _use_memory_fallback
    if _use_memory_fallback:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await _redis_client.ping()
        return _redis_client
    except Exception:
        log.warning("Redis unavailable at %s, using in-memory fallback", REDIS_URL)
        _use_memory_fallback = True
        return None


def use_memory_backend() -> None:
    """Force the in-memory backend (for tests)."""
    global _use_memory_fallback, _redis_client
    _use_memory_fallback = True
    _redis_client = None


def reset_backend() -> None:
    """Reset to Redis backend (for teardown)."""
    global _use_memory_fallback, _redis_client
    _use_memory_fallback = False
    _redis_client = None
    _memory_store.clear()


# ── Highlight service ────────────────────────────────────────────────────────


class HighlightService:
    """User-scoped geometry working set."""

    async def add(
        self,
        user_id: UUID,
        field_ids: list[UUID],
        ttl: int = DEFAULT_TTL_SECONDS,
    ) -> list[str]:
        """Add field IDs to the user's highlight set. Returns the full set."""
        r = await get_redis()
        key = _user_key(user_id)

        if r is not None:
            if field_ids:
                await r.sadd(key, *[str(fid) for fid in field_ids])
            await r.expire(key, ttl)
            members = await r.smembers(key)
            return sorted(members)
        else:
            # Memory fallback
            if key not in _memory_store:
                _memory_store[key] = {"members": set(), "ttl": ttl}
            _memory_store[key]["members"].update(str(fid) for fid in field_ids)
            return sorted(_memory_store[key]["members"])

    async def remove(self, user_id: UUID, field_ids: list[UUID]) -> list[str]:
        """Remove field IDs from the highlight set. Returns the remaining set."""
        r = await get_redis()
        key = _user_key(user_id)

        if r is not None:
            if field_ids:
                await r.srem(key, *[str(fid) for fid in field_ids])
            members = await r.smembers(key)
            return sorted(members)
        else:
            if key in _memory_store:
                for fid in field_ids:
                    _memory_store[key]["members"].discard(str(fid))
                return sorted(_memory_store[key]["members"])
            return []

    async def list(self, user_id: UUID) -> list[str]:
        """Return all field IDs in the user's highlight set."""
        r = await get_redis()
        key = _user_key(user_id)

        if r is not None:
            members = await r.smembers(key)
            return sorted(members)
        else:
            if key in _memory_store:
                return sorted(_memory_store[key]["members"])
            return []

    async def clear(self, user_id: UUID) -> None:
        """Clear the user's highlight set."""
        r = await get_redis()
        key = _user_key(user_id)

        if r is not None:
            await r.delete(key)
        else:
            _memory_store.pop(key, None)

    async def count(self, user_id: UUID) -> int:
        """Return the number of items in the highlight set."""
        r = await get_redis()
        key = _user_key(user_id)

        if r is not None:
            return await r.scard(key)
        else:
            if key in _memory_store:
                return len(_memory_store[key]["members"])
            return 0


# ── Geometry operations on the working set ───────────────────────────────────


class HighlightGeometryService:
    """Spatial operations on the highlighted working set.

    These operations query the actual field geometries from the database
    and return the result as GeoJSON.
    """

    def __init__(self, db) -> None:
        from sqlalchemy.ext.asyncio import AsyncSession

        self.db: AsyncSession = db

    async def _get_geometries_wkt(self, field_ids: list[UUID]) -> list[str]:
        """Fetch WKT geometries for the given field IDs."""
        from geoalchemy2.functions import ST_AsText
        from sqlalchemy import select

        from openfmis.models.field import Field

        result = await self.db.execute(
            select(
                ST_AsText(Field.geometry).label("wkt"),
            ).where(
                Field.id.in_(field_ids),
                Field.deleted_at.is_(None),
                Field.is_current.is_(True),
                Field.geometry.isnot(None),
            )
        )
        return [row.wkt for row in result if row.wkt]

    async def merge(self, field_ids: list[UUID]) -> dict | None:
        """Union all highlighted geometries into one. Returns GeoJSON."""
        from shapely import from_wkt, ops, to_geojson

        wkts = await self._get_geometries_wkt(field_ids)
        if not wkts:
            return None

        geoms = [from_wkt(w) for w in wkts]
        merged = ops.unary_union(geoms)
        return json.loads(to_geojson(merged))

    async def clip(self, field_ids: list[UUID], clip_geometry: dict) -> dict | None:
        """Clip the union of highlighted geometries by a clip polygon.

        Returns the intersection as GeoJSON.
        """
        from shapely import from_geojson, from_wkt, ops, to_geojson

        wkts = await self._get_geometries_wkt(field_ids)
        if not wkts:
            return None

        geoms = [from_wkt(w) for w in wkts]
        merged = ops.unary_union(geoms)
        clip_geom = from_geojson(json.dumps(clip_geometry))
        clipped = merged.intersection(clip_geom)
        if clipped.is_empty:
            return None
        return json.loads(to_geojson(clipped))

    async def hole(self, field_ids: list[UUID], hole_geometry: dict) -> dict | None:
        """Cut a hole in the union of highlighted geometries.

        Returns the difference as GeoJSON.
        """
        from shapely import from_geojson, from_wkt, ops, to_geojson

        wkts = await self._get_geometries_wkt(field_ids)
        if not wkts:
            return None

        geoms = [from_wkt(w) for w in wkts]
        merged = ops.unary_union(geoms)
        hole_geom = from_geojson(json.dumps(hole_geometry))
        result = merged.difference(hole_geom)
        if result.is_empty:
            return None
        return json.loads(to_geojson(result))
