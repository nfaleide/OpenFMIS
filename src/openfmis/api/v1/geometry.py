"""Geometry spatial operation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.geometry import (
    BboxResponse,
    BufferInput,
    CentroidResponse,
    ClipInput,
    GeometryArea,
    GeometryInput,
    GeometryType,
    GeometryValidation,
    HoleInput,
    IntersectionQuery,
    IntersectionResponse,
    IntersectionResult,
    MultiGeometryInput,
)
from openfmis.services.geometry import GeometryService

router = APIRouter(prefix="/geometry", tags=["geometry"])


@router.post("/validate", response_model=GeometryValidation)
async def validate_geometry(
    body: GeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GeometryValidation:
    svc = GeometryService(db)
    is_valid, reason = await svc.validate(body.geometry)
    return GeometryValidation(is_valid=is_valid, reason=reason)


@router.post("/area", response_model=GeometryArea)
async def calculate_area(
    body: GeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GeometryArea:
    svc = GeometryService(db)
    area_acres, area_sq_meters = await svc.calculate_area(body.geometry)
    return GeometryArea(area_acres=area_acres, area_sq_meters=area_sq_meters)


@router.post("/bbox", response_model=BboxResponse)
async def calculate_bbox(
    body: GeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BboxResponse:
    svc = GeometryService(db)
    min_lon, min_lat, max_lon, max_lat, area_acres = await svc.calculate_bbox_area(body.geometry)
    return BboxResponse(
        min_longitude=min_lon,
        min_latitude=min_lat,
        max_longitude=max_lon,
        max_latitude=max_lat,
        area_acres=area_acres,
    )


@router.post("/type", response_model=GeometryType)
async def get_geometry_type(
    body: GeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> GeometryType:
    svc = GeometryService(db)
    geom_type, num_geoms = await svc.get_type(body.geometry)
    return GeometryType(geometry_type=geom_type, num_geometries=num_geoms)


@router.post("/centroid", response_model=CentroidResponse)
async def get_centroid(
    body: GeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CentroidResponse:
    svc = GeometryService(db)
    lon, lat = await svc.centroid(body.geometry)
    return CentroidResponse(longitude=lon, latitude=lat)


@router.post("/union", response_model=dict)
async def union_geometries(
    body: MultiGeometryInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Union multiple geometries into one. Returns GeoJSON geometry."""
    svc = GeometryService(db)
    result = await svc.union(body.geometries)
    return result


@router.post("/clip", response_model=dict)
async def clip_geometry(
    body: ClipInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Clip geometry by another (intersection). Returns GeoJSON."""
    svc = GeometryService(db)
    result = await svc.clip(body.geometry, body.clip_geometry)
    return result


@router.post("/hole", response_model=dict)
async def hole_geometry(
    body: HoleInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Punch a hole in geometry (difference). Returns GeoJSON."""
    svc = GeometryService(db)
    result = await svc.hole(body.geometry, body.hole_geometry)
    return result


@router.post("/buffer", response_model=dict)
async def buffer_geometry(
    body: BufferInput,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Buffer geometry by distance in meters. Returns GeoJSON."""
    svc = GeometryService(db)
    result = await svc.buffer(body.geometry, body.distance_meters)
    return result


@router.post("/intersections", response_model=IntersectionResponse)
async def find_intersections(
    body: IntersectionQuery,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IntersectionResponse:
    """Find stored fields that intersect the given geometry."""
    svc = GeometryService(db)
    results = await svc.find_intersecting_fields(body.geometry, body.group_id)
    items = [IntersectionResult(**r) for r in results]
    return IntersectionResponse(intersecting_fields=items, total=len(items))
