"""SceneDiscoveryService — query STAC catalogs for satellite scenes and cache results.

Supports multiple collections: Sentinel-2 L2A, Sentinel-1 GRD, Landsat C2 L2.
"""

from __future__ import annotations

import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import SceneRecord
from openfmis.services.band_registry import CollectionProfile, get_profile, list_profiles

log = logging.getLogger(__name__)


class SceneDiscoveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── STAC search ───────────────────────────────────────────────────────

    async def search_scenes(
        self,
        geometry: dict,
        date_from: datetime,
        date_to: datetime,
        cloud_cover_max: float = 30.0,
        limit: int = 10,
        collection: str = "sentinel-2-l2a",
        collections: list[str] | None = None,
    ) -> list[dict]:
        """Search STAC for scenes covering *geometry*.

        Can search a single collection or multiple collections at once.
        Returns lightweight scene dicts (not yet cached).
        """
        if collections:
            # Multi-source search
            all_results = []
            for coll in collections:
                results = await self._search_single(
                    geometry, date_from, date_to, cloud_cover_max, limit, coll
                )
                all_results.extend(results)
            all_results.sort(key=lambda s: s.get("acquired_at", ""), reverse=True)
            return all_results[:limit]

        return await self._search_single(
            geometry, date_from, date_to, cloud_cover_max, limit, collection
        )

    async def _search_single(
        self,
        geometry: dict,
        date_from: datetime,
        date_to: datetime,
        cloud_cover_max: float,
        limit: int,
        collection: str,
    ) -> list[dict]:
        profile = get_profile(collection)
        if profile.stac_endpoint is None:
            return []  # custom uploads don't have STAC endpoints

        datetime_str = (
            f"{date_from.strftime('%Y-%m-%dT%H:%M:%SZ')}/{date_to.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        payload: dict = {
            "collections": [profile.stac_collection],
            "intersects": geometry,
            "datetime": datetime_str,
            "limit": limit,
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }

        # Only add cloud cover filter for optical sensors
        if profile.sensor_type == "optical":
            payload["query"] = {"eo:cloud_cover": {"lte": cloud_cover_max}}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{profile.stac_endpoint}/search",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        return [_stac_item_to_dict(item, profile) for item in data.get("features", [])]

    async def get_scene_by_id(self, scene_id: str) -> dict | None:
        """Return scene from DB cache, or fetch from STAC if not cached."""
        cached = await self._get_cached(scene_id)
        if cached:
            return _record_to_dict(cached)

        # Try each known STAC endpoint
        for profile in list_profiles():
            if profile.stac_endpoint is None or profile.stac_collection is None:
                continue
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(
                        f"{profile.stac_endpoint}/collections/{profile.stac_collection}/items/{scene_id}"
                    )
                    if resp.status_code == 404:
                        continue
                    resp.raise_for_status()
                    item = resp.json()
                record = await self.cache_scene(item, profile.collection_id)
                return _record_to_dict(record)
            except Exception:
                continue

        return None

    async def cache_scene(self, stac_item: dict, collection: str = "sentinel-2-l2a") -> SceneRecord:
        """Persist a STAC item to the local scene cache (upsert by scene_id)."""
        scene_id = stac_item["id"]
        existing = await self._get_cached(scene_id)
        if existing:
            return existing

        profile = get_profile(collection)
        props = stac_item.get("properties", {})
        acquired_at = datetime.fromisoformat(props.get("datetime", "").replace("Z", "+00:00"))
        cloud_cover = props.get("eo:cloud_cover")
        bbox = stac_item.get("bbox")
        assets = _extract_assets(stac_item.get("assets", {}), profile)

        # Build footprint WKT from item geometry
        geom = stac_item.get("geometry")
        footprint_wkt = None
        if geom:
            footprint_wkt = _geometry_to_ewkt(geom)

        record = SceneRecord(
            scene_id=scene_id,
            collection=collection,
            acquired_at=acquired_at,
            cloud_cover=cloud_cover,
            bbox=bbox,
            assets=assets,
            stac_properties=props,
            footprint=footprint_wkt,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    # ── DB helpers ────────────────────────────────────────────────────────

    async def _get_cached(self, scene_id: str) -> SceneRecord | None:
        result = await self.db.execute(select(SceneRecord).where(SceneRecord.scene_id == scene_id))
        return result.scalar_one_or_none()

    async def list_cached_scenes(
        self,
        limit: int = 50,
        offset: int = 0,
        collection: str | None = None,
    ) -> list[dict]:
        stmt = select(SceneRecord)
        if collection:
            stmt = stmt.where(SceneRecord.collection == collection)
        result = await self.db.execute(
            stmt.order_by(SceneRecord.acquired_at.desc()).offset(offset).limit(limit)
        )
        return [_record_to_dict(r) for r in result.scalars().all()]

    async def get_available_collections(self) -> list[dict]:
        """Return info about all supported satellite collections."""
        return [
            {
                "collection_id": p.collection_id,
                "display_name": p.display_name,
                "sensor_type": p.sensor_type,
                "available_bands": sorted(set(p.band_map.values())),
                "description": p.description,
            }
            for p in list_profiles()
            if p.stac_endpoint is not None
        ]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _coords_to_wkt(ring: list) -> str:
    return ", ".join(f"{lon} {lat}" for lon, lat in ring)


def _geometry_to_ewkt(geom: dict) -> str | None:
    if geom["type"] == "Polygon":
        coords_str = _coords_to_wkt(geom["coordinates"][0])
        return f"SRID=4326;MULTIPOLYGON((({coords_str})))"
    elif geom["type"] == "MultiPolygon":
        parts = ", ".join(f"(({_coords_to_wkt(ring[0])}))" for ring in geom["coordinates"])
        return f"SRID=4326;MULTIPOLYGON({parts})"
    return None


def _extract_assets(raw_assets: dict, profile: CollectionProfile) -> dict:
    """Pull band hrefs, mapping STAC asset keys to common band names."""
    out: dict[str, str] = {}
    for key, val in raw_assets.items():
        if isinstance(val, dict) and "href" in val:
            common_name = profile.band_map.get(key)
            if common_name:
                out[common_name] = val["href"]
            else:
                # Keep the original key for non-mapped assets
                out[key] = val["href"]
    return out


def _stac_item_to_dict(item: dict, profile: CollectionProfile) -> dict:
    props = item.get("properties", {})
    return {
        "scene_id": item["id"],
        "collection": profile.collection_id,
        "acquired_at": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "bbox": item.get("bbox"),
        "assets": _extract_assets(item.get("assets", {}), profile),
        "stac_properties": props,
        "sensor_type": profile.sensor_type,
    }


def _record_to_dict(r: SceneRecord) -> dict:
    return {
        "scene_id": r.scene_id,
        "collection": r.collection,
        "acquired_at": r.acquired_at.isoformat(),
        "cloud_cover": r.cloud_cover,
        "bbox": r.bbox,
        "assets": r.assets,
        "stac_properties": r.stac_properties,
        "cached": True,
    }
