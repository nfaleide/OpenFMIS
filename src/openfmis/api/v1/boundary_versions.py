"""FieldBoundaryVersion endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, verify_field_access
from openfmis.models.user import User
from openfmis.schemas.field_boundary_version import (
    BoundaryVersionCreate,
    BoundaryVersionDetail,
    BoundaryVersionOut,
)
from openfmis.services.field_boundary_version import FieldBoundaryVersionService

router = APIRouter(prefix="/boundary-versions", tags=["boundary-versions"])


@router.get("", response_model=list[BoundaryVersionOut], summary="List boundary versions")
async def list_boundary_versions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
) -> list[BoundaryVersionOut]:
    svc = FieldBoundaryVersionService(db)
    if field_id is None:
        return []
    await verify_field_access(current_user, field_id, db)
    items = await svc.list_by_field(field_id)
    return [BoundaryVersionOut.model_validate(v) for v in items]


@router.get("/{version_id}", response_model=BoundaryVersionDetail, summary="Get boundary version")
async def get_boundary_version(
    version_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BoundaryVersionDetail:
    svc = FieldBoundaryVersionService(db)
    v = await svc.get_by_id(version_id)
    await verify_field_access(current_user, v.field_id, db)
    geojson = await svc.get_geometry_geojson(version_id)
    data = BoundaryVersionOut.model_validate(v).model_dump()
    data["geometry_geojson"] = geojson
    return BoundaryVersionDetail(**data)


@router.post(
    "",
    response_model=BoundaryVersionOut,
    status_code=201,
    summary="Create boundary version",
)
async def create_boundary_version(
    body: BoundaryVersionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> BoundaryVersionOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = FieldBoundaryVersionService(db)
    v = await svc.create(body, created_by=current_user.id)
    return BoundaryVersionOut.model_validate(v)
