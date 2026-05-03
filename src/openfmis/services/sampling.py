"""Sampling service — CRUD + point generation for sampling plans."""

from __future__ import annotations

import copy
import json
import logging
import uuid
from typing import Any

from geoalchemy2.functions import ST_AsGeoJSON
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.core.events import event_bus
from openfmis.models.sampling import SamplingPlan
from openfmis.schemas.sampling import (
    SamplingPlanCreate,
    SamplingPlanRegenerate,
    SamplingPlanUpdate,
)
from openfmis.services.sampling_algorithms import generate_points

log = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────


class SamplingPlanNotFoundError(Exception):
    pass


class FieldGeometryNotFoundError(Exception):
    pass


# ── Helpers ──────────────────────────────────────────────────────────────────


def _points_to_wkt(points: list[tuple[float, float]]) -> str:
    """Convert list of (lon, lat) to WKT MULTIPOINT."""
    coords = ", ".join(f"{lon} {lat}" for lon, lat in points)
    return f"SRID=4326;MULTIPOINT({coords})"


def _points_to_geojson(points: list[tuple[float, float]]) -> dict[str, Any]:
    """Convert list of (lon, lat) to GeoJSON FeatureCollection."""
    features = []
    for i, (lon, lat) in enumerate(points):
        features.append(
            {
                "type": "Feature",
                "properties": {"index": i, "completed": False},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _val(x: object) -> str:
    return x.value if hasattr(x, "value") else x


# ── Service ──────────────────────────────────────────────────────────────────


class SamplingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Geometry helpers ─────────────────────────────────────────────────

    async def _get_field_geometry(self, field_id: uuid.UUID) -> Any:
        """Return the Shapely polygon for a field."""
        from openfmis.models.field import Field

        result = await self.db.execute(
            select(ST_AsGeoJSON(Field.geometry).label("geojson")).where(Field.id == field_id)
        )
        row = result.first()
        if row is None or row.geojson is None:
            raise FieldGeometryNotFoundError(f"No geometry for field {field_id}")
        return shape(json.loads(row.geojson))

    # ── Create ───────────────────────────────────────────────────────────

    async def create_plan(
        self,
        data: SamplingPlanCreate,
        created_by: uuid.UUID,
    ) -> SamplingPlan:
        # Resolve geometry
        polygon = await self._get_field_geometry(data.field_id)

        # Generate sample points
        points = generate_points(
            polygon=polygon,
            algorithm=data.algorithm,
            count=data.point_count,
            min_distance=data.min_distance,
            buffer_distance=data.buffer_distance,
            cluster_count=data.cluster_count or 3,
            min_cluster_distance=data.min_cluster_distance or 0.0,
        )

        plan = SamplingPlan(
            name=data.name,
            description=data.description,
            field_id=data.field_id,
            zone_id=data.zone_id,
            created_by=created_by,
            algorithm=data.algorithm,
            point_count=len(points),
            min_distance=data.min_distance,
            buffer_distance=data.buffer_distance,
            cluster_count=data.cluster_count,
            min_cluster_distance=data.min_cluster_distance,
            points=_points_to_wkt(points) if points else None,
            points_geojson=_points_to_geojson(points),
        )
        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)

        await event_bus.emit(
            "sampling.plan.created",
            {"plan_id": str(plan.id), "field_id": str(data.field_id), "algorithm": data.algorithm},
        )
        return plan

    # ── Read ─────────────────────────────────────────────────────────────

    async def get_plan(self, plan_id: uuid.UUID) -> SamplingPlan:
        result = await self.db.execute(select(SamplingPlan).where(SamplingPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if plan is None:
            raise SamplingPlanNotFoundError(str(plan_id))
        return plan

    async def list_plans(
        self,
        field_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SamplingPlan]:
        stmt = select(SamplingPlan)
        if field_id:
            stmt = stmt.where(SamplingPlan.field_id == field_id)
        if created_by:
            stmt = stmt.where(SamplingPlan.created_by == created_by)
        if status:
            stmt = stmt.where(SamplingPlan.status == status)
        stmt = stmt.order_by(SamplingPlan.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ── Update ───────────────────────────────────────────────────────────

    async def update_plan(
        self,
        plan_id: uuid.UUID,
        data: SamplingPlanUpdate,
    ) -> SamplingPlan:
        plan = await self.get_plan(plan_id)
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(plan, key, value)
        await self.db.flush()
        await self.db.refresh(plan)
        return plan

    # ── Regenerate ───────────────────────────────────────────────────────

    async def regenerate_points(
        self,
        plan_id: uuid.UUID,
        data: SamplingPlanRegenerate,
    ) -> SamplingPlan:
        plan = await self.get_plan(plan_id)

        # Apply any overrides
        overrides = data.model_dump(exclude_unset=True)
        for key, value in overrides.items():
            setattr(plan, key, value)

        # Resolve geometry
        polygon = await self._get_field_geometry(plan.field_id)

        points = generate_points(
            polygon=polygon,
            algorithm=_val(plan.algorithm),
            count=plan.point_count,
            min_distance=plan.min_distance,
            buffer_distance=plan.buffer_distance,
            cluster_count=plan.cluster_count or 3,
            min_cluster_distance=plan.min_cluster_distance or 0.0,
        )

        plan.point_count = len(points)
        plan.points = _points_to_wkt(points) if points else None
        plan.points_geojson = _points_to_geojson(points)
        plan.points_completed = 0

        await self.db.flush()
        await self.db.refresh(plan)
        return plan

    # ── Delete ───────────────────────────────────────────────────────────

    async def delete_plan(self, plan_id: uuid.UUID) -> None:
        plan = await self.get_plan(plan_id)
        await self.db.delete(plan)
        await self.db.flush()

    # ── Mark point complete ──────────────────────────────────────────

    async def mark_point_completed(
        self,
        plan_id: uuid.UUID,
        point_index: int,
        notes: str | None = None,
    ) -> SamplingPlan:
        plan = await self.get_plan(plan_id)

        # Deep copy to ensure SQLAlchemy detects the JSONB mutation
        if plan.points_geojson and "features" in plan.points_geojson:
            updated_geojson = copy.deepcopy(plan.points_geojson)
            features = updated_geojson["features"]
            if 0 <= point_index < len(features):
                features[point_index]["properties"]["completed"] = True
                if notes:
                    features[point_index]["properties"]["notes"] = notes
            plan.points_geojson = updated_geojson

        plan.points_completed = (
            sum(
                1
                for f in plan.points_geojson.get("features", [])
                if f.get("properties", {}).get("completed")
            )
            if plan.points_geojson
            else 0
        )

        # Auto-complete plan if all points collected
        if plan.points_completed >= plan.point_count:
            plan.status = "completed"

        await self.db.flush()
        await self.db.refresh(plan)
        return plan

    # ── Export ───────────────────────────────────────────────────────

    async def export_plan(
        self,
        plan_id: uuid.UUID,
        fmt: str = "geojson",
    ) -> dict[str, Any]:
        """Export a sampling plan as GeoJSON or CSV."""
        plan = await self.get_plan(plan_id)
        if not plan.points_geojson or "features" not in plan.points_geojson:
            raise ValueError("Plan has no generated points")

        features = plan.points_geojson["features"]
        completed_count = sum(1 for f in features if f.get("properties", {}).get("completed"))

        if fmt == "csv":
            content = self._export_csv(plan, features)
        else:
            content = self._export_geojson(plan, features)

        return {
            "plan_name": plan.name,
            "format": fmt,
            "point_count": len(features),
            "completed_count": completed_count,
            "content": content,
        }

    def _export_geojson(self, plan: SamplingPlan, features: list) -> str:
        """Serialize plan points to a GeoJSON FeatureCollection string."""
        export_features = []
        for f in features:
            props = f.get("properties", {})
            coords = f["geometry"]["coordinates"]
            export_features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": coords},
                    "properties": {
                        "point_id": props.get("index", 0) + 1,
                        "status": "completed" if props.get("completed") else "pending",
                        "planned_lng": coords[0],
                        "planned_lat": coords[1],
                        "notes": props.get("notes"),
                    },
                }
            )

        fc = {
            "type": "FeatureCollection",
            "properties": {
                "plan_name": plan.name,
                "plan_id": str(plan.id),
                "algorithm": _val(plan.algorithm),
                "total_points": len(features),
                "completed_points": plan.points_completed,
            },
            "features": export_features,
        }
        return json.dumps(fc, indent=2)

    def _export_csv(self, plan: SamplingPlan, features: list) -> str:
        """Serialize plan points to CSV string."""
        header = "point_id,planned_lat,planned_lng,status,notes"
        rows = [header]
        for f in features:
            props = f.get("properties", {})
            coords = f["geometry"]["coordinates"]
            status = "completed" if props.get("completed") else "pending"
            notes = (props.get("notes") or "").replace(",", ";")
            rows.append(f"{props.get('index', 0) + 1},{coords[1]},{coords[0]},{status},{notes}")
        return "\n".join(rows)
