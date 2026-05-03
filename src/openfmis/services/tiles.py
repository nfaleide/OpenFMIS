"""TileServingService — serve PostGIS geometry as Mapbox Vector Tiles (MVT).

Each endpoint pattern:  /tiles/{layer}/{z}/{x}/{y}.mvt
Supported layers: fields, clu, plss_townships, plss_sections

Tiles are built server-side with ST_AsMVT + ST_TileEnvelope.
No external tile server required.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Maximum zoom we'll serve (beyond this geometry is too detailed to be useful as MVT)
MAX_ZOOM = 18
MIN_ZOOM = 4

VALID_LAYERS = {"fields", "clu", "plss_townships", "plss_sections"}


class TileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_tile(self, layer: str, z: int, x: int, y: int) -> bytes | None:
        """Return raw MVT bytes for the requested tile, or None if empty."""
        from openfmis.plugin_sdk.hooks import get_tile_layer

        is_core = layer in VALID_LAYERS
        plugin_spec = get_tile_layer(layer) if not is_core else None

        if not is_core and plugin_spec is None:
            all_layers = sorted(VALID_LAYERS | set(list_plugin_tile_layers()))
            raise ValueError(f"Unknown layer: {layer!r}. Valid: {all_layers}")

        if not (MIN_ZOOM <= z <= MAX_ZOOM):
            return None

        if is_core:
            sql = _build_tile_sql(layer, z, x, y)
        else:
            assert plugin_spec is not None
            sql = plugin_spec.sql_builder(z, x, y)
            if not sql:
                return None

        result = await self.db.execute(text(sql), {"z": z, "x": x, "y": y})
        row = result.fetchone()
        if row is None:
            return None
        mvt_bytes = row[0]
        # ST_AsMVT returns NULL or empty bytes when no features intersect
        if not mvt_bytes:
            return None
        return bytes(mvt_bytes)


def list_plugin_tile_layers() -> list[str]:
    """Return names of plugin-registered tile layers."""
    from openfmis.plugin_sdk.hooks import list_tile_layers

    return list_tile_layers()


# ── SQL builders ──────────────────────────────────────────────────────────────


def _build_tile_sql(layer: str, z: int, x: int, y: int) -> str:
    """Return a parameterised SQL string for the given layer."""
    envelope = "ST_TileEnvelope(:z, :x, :y)"

    if layer == "fields":
        return f"""
        WITH tile AS (
            SELECT
                f.id::text            AS id,
                f.name,
                f.group_id::text      AS group_id,
                f.version,
                f.area_acres,
                ST_AsMVTGeom(
                    ST_Transform(f.geometry, 3857),
                    {envelope},
                    4096, 64, true
                ) AS geom
            FROM fields f
            WHERE
                f.deleted_at IS NULL
                AND f.is_current = true
                AND f.geometry IS NOT NULL
                AND ST_Intersects(f.geometry, ST_Transform({envelope}, 4326))
        )
        SELECT ST_AsMVT(tile, 'fields', 4096, 'geom') FROM tile
        """

    if layer == "clu":
        return f"""
        WITH tile AS (
            SELECT
                c.id::text            AS id,
                c.state,
                c.county_fips,
                c.calcacres,
                ST_AsMVTGeom(
                    ST_Transform(c.geom, 3857),
                    {envelope},
                    4096, 64, true
                ) AS geom
            FROM clu c
            WHERE
                c.geom IS NOT NULL
                AND ST_Intersects(c.geom, ST_Transform({envelope}, 4326))
        )
        SELECT ST_AsMVT(tile, 'clu', 4096, 'geom') FROM tile
        """

    if layer == "plss_townships":
        return f"""
        WITH tile AS (
            SELECT
                t.id::text            AS id,
                t.lndkey,
                t.state,
                t.label,
                t.fips_c,
                ST_AsMVTGeom(
                    ST_Transform(t.geom, 3857),
                    {envelope},
                    4096, 64, true
                ) AS geom
            FROM plss_townships t
            WHERE
                t.geom IS NOT NULL
                AND ST_Intersects(t.geom, ST_Transform({envelope}, 4326))
        )
        SELECT ST_AsMVT(tile, 'plss_townships', 4096, 'geom') FROM tile
        """

    if layer == "plss_sections":
        return f"""
        WITH tile AS (
            SELECT
                s.id::text            AS id,
                s.lndkey,
                s.mtrs,
                s.sectn,
                s.label,
                s.fips_c,
                ST_AsMVTGeom(
                    ST_Transform(s.geom, 3857),
                    {envelope},
                    4096, 64, true
                ) AS geom
            FROM plss_sections s
            WHERE
                s.geom IS NOT NULL
                AND ST_Intersects(s.geom, ST_Transform({envelope}, 4326))
        )
        SELECT ST_AsMVT(tile, 'plss_sections', 4096, 'geom') FROM tile
        """

    raise ValueError(f"No SQL builder for layer: {layer}")
