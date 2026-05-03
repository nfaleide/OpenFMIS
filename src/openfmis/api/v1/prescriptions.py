"""Prescription + InterpolationSurface endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import (
    get_current_user,
    verify_entity_group_access,
    verify_field_access,
)
from openfmis.models.prescription import InterpolationSurface, Prescription
from openfmis.models.user import User
from openfmis.schemas.prescription import (
    InterpolationSurfaceCreate,
    InterpolationSurfaceOut,
    PrescriptionCreate,
    PrescriptionDetail,
    PrescriptionOut,
    PrescriptionUpdate,
)
from openfmis.services.prescription import InterpolationSurfaceService, PrescriptionService

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


# ── Interpolation surfaces ─────────────────────────────────────────────────


@router.get("/surfaces", response_model=list[InterpolationSurfaceOut], summary="List surfaces")
async def list_surfaces(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
) -> list[InterpolationSurfaceOut]:
    svc = InterpolationSurfaceService(db)
    if field_id is None:
        return []
    await verify_field_access(current_user, field_id, db)
    items = await svc.list_by_field(field_id)
    return [InterpolationSurfaceOut.model_validate(s) for s in items]


@router.get("/surfaces/{surface_id}", response_model=InterpolationSurfaceOut, summary="Get surface")
async def get_surface(
    surface_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InterpolationSurfaceOut:
    await verify_entity_group_access(
        current_user, surface_id, InterpolationSurface, db, label="Surface"
    )
    svc = InterpolationSurfaceService(db)
    s = await svc.get_by_id(surface_id)
    return InterpolationSurfaceOut.model_validate(s)


@router.post(
    "/surfaces",
    response_model=InterpolationSurfaceOut,
    status_code=201,
    summary="Create surface",
)
async def create_surface(
    body: InterpolationSurfaceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InterpolationSurfaceOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = InterpolationSurfaceService(db)
    s = await svc.create(body)
    return InterpolationSurfaceOut.model_validate(s)


# ── Prescriptions ──────────────────────────────────────────────────────────


@router.get("", response_model=list[PrescriptionOut], summary="List prescriptions")
async def list_prescriptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
    crop_year_id: UUID | None = None,
) -> list[PrescriptionOut]:
    if field_id is not None:
        await verify_field_access(current_user, field_id, db)
    svc = PrescriptionService(db)
    items = await svc.list_prescriptions(field_id=field_id, crop_year_id=crop_year_id)
    return [PrescriptionOut.model_validate(p) for p in items]


@router.get("/{prescription_id}", response_model=PrescriptionDetail, summary="Get prescription")
async def get_prescription(
    prescription_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PrescriptionDetail:
    await verify_entity_group_access(
        current_user, prescription_id, Prescription, db, label="Prescription"
    )
    svc = PrescriptionService(db)
    p = await svc.get_by_id(prescription_id)
    geojson = await svc.get_geometry_geojson(prescription_id)
    data = PrescriptionOut.model_validate(p).model_dump()
    data["geometry_geojson"] = geojson
    return PrescriptionDetail(**data)


@router.post("", response_model=PrescriptionOut, status_code=201, summary="Create prescription")
async def create_prescription(
    body: PrescriptionCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PrescriptionOut:
    await verify_field_access(current_user, body.field_id, db)
    svc = PrescriptionService(db)
    p = await svc.create(body)
    return PrescriptionOut.model_validate(p)


@router.patch("/{prescription_id}", response_model=PrescriptionOut, summary="Update prescription")
async def update_prescription(
    prescription_id: UUID,
    body: PrescriptionUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> PrescriptionOut:
    await verify_entity_group_access(
        current_user, prescription_id, Prescription, db, label="Prescription"
    )
    svc = PrescriptionService(db)
    p = await svc.update(prescription_id, body)
    return PrescriptionOut.model_validate(p)


@router.delete("/{prescription_id}", status_code=204, summary="Delete prescription")
async def delete_prescription(
    prescription_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    await verify_entity_group_access(
        current_user, prescription_id, Prescription, db, label="Prescription"
    )
    svc = PrescriptionService(db)
    await svc.soft_delete(prescription_id)
