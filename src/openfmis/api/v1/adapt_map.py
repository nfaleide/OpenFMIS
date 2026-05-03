"""ADAPT entity mapping endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, verify_group_access
from openfmis.exceptions import NotFoundError, ValidationError
from openfmis.models.user import User
from openfmis.schemas.adapt_map import ADAPTMapCreate, ADAPTMapOut, ADAPTMapUpsert
from openfmis.services.adapt_export import ADAPTExportService
from openfmis.services.adapt_import import ADAPTImportService
from openfmis.services.adapt_map import ADAPTMapService

router = APIRouter(prefix="/adapt-map", tags=["adapt-map"])


@router.get("", response_model=list[ADAPTMapOut], summary="List mappings")
async def list_mappings(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    internal_type: str | None = None,
) -> list[ADAPTMapOut]:
    svc = ADAPTMapService(db)
    if internal_type is None:
        return []
    items = await svc.list_by_type(internal_type)
    return [ADAPTMapOut.model_validate(m) for m in items]


@router.get("/{map_id}", response_model=ADAPTMapOut, summary="Get mapping")
async def get_mapping(
    map_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ADAPTMapOut:
    svc = ADAPTMapService(db)
    m = await svc.get_by_id(map_id)
    return ADAPTMapOut.model_validate(m)


@router.get(
    "/lookup/{internal_type}/{internal_id}",
    response_model=ADAPTMapOut,
    summary="Lookup mapping",
)
async def lookup_mapping(
    internal_type: str,
    internal_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ADAPTMapOut:
    svc = ADAPTMapService(db)
    m = await svc.lookup(internal_type, internal_id)
    if m is None:
        raise HTTPException(404, "ADAPT mapping not found")
    return ADAPTMapOut.model_validate(m)


@router.post("", response_model=ADAPTMapOut, status_code=201, summary="Create mapping")
async def create_mapping(
    body: ADAPTMapCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ADAPTMapOut:
    svc = ADAPTMapService(db)
    m = await svc.create(body)
    return ADAPTMapOut.model_validate(m)


@router.put("", response_model=ADAPTMapOut, summary="Upsert mapping")
async def upsert_mapping(
    body: ADAPTMapUpsert,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ADAPTMapOut:
    svc = ADAPTMapService(db)
    m = await svc.upsert(body)
    return ADAPTMapOut.model_validate(m)


@router.delete("/{map_id}", status_code=204, summary="Delete mapping")
async def delete_mapping(
    map_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = ADAPTMapService(db)
    await svc.delete(map_id)


@router.get("/export/{group_id}", summary="Export adapt")
async def export_adapt(
    group_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    await verify_group_access(current_user, group_id)
    svc = ADAPTExportService(db)
    try:
        return await svc.export_group(group_id)
    except NotFoundError:
        raise HTTPException(404, "Group not found")


@router.post("/import", summary="Import adapt")
async def import_adapt(
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    target_group_id: UUID | None = None,
) -> dict:
    """Import ADAPT JSON hierarchy into OpenFMIS.

    Accepts a Grower, Farm, or Field document. Creates corresponding
    groups, regions, fields, and crop years with ADAPT entity mappings.
    """
    if target_group_id is not None:
        await verify_group_access(current_user, target_group_id)

    svc = ADAPTImportService(db)
    try:
        result = await svc.import_adapt_json(
            body,
            target_group_id=target_group_id,
            created_by=current_user.id,
        )
    except ValidationError as exc:
        raise HTTPException(422, str(exc))

    return {
        "groups_created": result.groups_created,
        "regions_created": result.regions_created,
        "fields_created": result.fields_created,
        "crop_years_created": result.crop_years_created,
        "mappings_created": result.mappings_created,
        "skipped": result.skipped,
        "warnings": result.warnings,
    }
