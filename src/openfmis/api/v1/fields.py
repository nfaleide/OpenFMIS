"""Field CRUD endpoints with geometry and versioning."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.field import (
    FieldCreate,
    FieldList,
    FieldRead,
    FieldReadWithGeometry,
    FieldUpdate,
    FieldVersionHistory,
)
from openfmis.services.field import FieldService

router = APIRouter(prefix="/fields", tags=["fields"])


@router.get("", response_model=FieldList)
async def list_fields(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    group_id: UUID | None = None,
    current_only: bool = True,
) -> FieldList:
    svc = FieldService(db)
    fields, total = await svc.list_fields(
        offset=offset, limit=limit, group_id=group_id, current_only=current_only
    )
    return FieldList(items=[FieldRead.model_validate(f) for f in fields], total=total)


@router.get("/{field_id}", response_model=FieldReadWithGeometry)
async def get_field(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldReadWithGeometry:
    svc = FieldService(db)
    field = await svc.get_by_id(field_id)
    geojson = await svc.get_geometry_geojson(field_id)
    data = FieldRead.model_validate(field).model_dump()
    data["geometry_geojson"] = geojson
    return FieldReadWithGeometry(**data)


@router.get("/{field_id}/versions", response_model=FieldVersionHistory)
async def get_field_versions(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldVersionHistory:
    svc = FieldService(db)
    versions = await svc.get_version_history(field_id)
    return FieldVersionHistory(versions=[FieldRead.model_validate(v) for v in versions])


@router.post("", response_model=FieldRead, status_code=201)
async def create_field(
    body: FieldCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    svc = FieldService(db)
    field = await svc.create_field(body, created_by=current_user.id)
    return FieldRead.model_validate(field)


@router.patch("/{field_id}", response_model=FieldRead)
async def update_field(
    field_id: UUID,
    body: FieldUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    svc = FieldService(db)
    field = await svc.update_field(field_id, body)
    return FieldRead.model_validate(field)


@router.put("/{field_id}/geometry", response_model=FieldRead)
async def update_field_geometry(
    field_id: UUID,
    geometry_geojson: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FieldRead:
    """Update field geometry — creates a new version."""
    svc = FieldService(db)
    new_field = await svc.update_geometry(field_id, geometry_geojson)
    return FieldRead.model_validate(new_field)


@router.delete("/{field_id}", status_code=204)
async def delete_field(
    field_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = FieldService(db)
    await svc.soft_delete(field_id)
