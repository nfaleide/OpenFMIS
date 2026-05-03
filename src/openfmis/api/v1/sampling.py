"""Sampling plugin API — plan creation, point generation, field collection."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.sampling import (
    ExportOut,
    SamplingPlanCreate,
    SamplingPlanOut,
    SamplingPlanRegenerate,
    SamplingPlanSummary,
    SamplingPlanUpdate,
)
from openfmis.services.sampling import (
    FieldGeometryNotFoundError,
    SamplingPlanNotFoundError,
    SamplingService,
)

router = APIRouter(prefix="/sampling", tags=["sampling"])


def _val(x: object) -> str:
    return x.value if hasattr(x, "value") else x


def _plan_out(plan) -> SamplingPlanOut:
    return SamplingPlanOut(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        field_id=plan.field_id,
        zone_id=plan.zone_id,
        created_by=plan.created_by,
        algorithm=_val(plan.algorithm),
        status=_val(plan.status),
        point_count=plan.point_count,
        min_distance=plan.min_distance,
        buffer_distance=plan.buffer_distance,
        cluster_count=plan.cluster_count,
        min_cluster_distance=plan.min_cluster_distance,
        points_geojson=plan.points_geojson,
        points_completed=plan.points_completed,
        collection_notes=plan.collection_notes,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.post("/plans", response_model=SamplingPlanOut, status_code=201, summary="Create plan")
async def create_plan(
    body: SamplingPlanCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SamplingPlanOut:
    svc = SamplingService(db)
    try:
        plan = await svc.create_plan(body, created_by=current_user.id)
    except FieldGeometryNotFoundError:
        raise HTTPException(404, "Field or zone geometry not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    await db.commit()
    return _plan_out(plan)


@router.get("/plans", response_model=list[SamplingPlanSummary], summary="List plans")
async def list_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    field_id: UUID | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> list[SamplingPlanSummary]:
    svc = SamplingService(db)
    plans = await svc.list_plans(
        field_id=field_id,
        created_by=current_user.id,
        status=status,
        offset=offset,
        limit=limit,
    )
    return [
        SamplingPlanSummary(
            id=p.id,
            name=p.name,
            field_id=p.field_id,
            algorithm=_val(p.algorithm),
            status=_val(p.status),
            point_count=p.point_count,
            points_completed=p.points_completed,
            created_at=p.created_at,
        )
        for p in plans
    ]


@router.get("/plans/{plan_id}", response_model=SamplingPlanOut, summary="Get plan")
async def get_plan(
    plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SamplingPlanOut:
    svc = SamplingService(db)
    try:
        plan = await svc.get_plan(plan_id)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    return _plan_out(plan)


@router.patch("/plans/{plan_id}", response_model=SamplingPlanOut, summary="Update plan")
async def update_plan(
    plan_id: UUID,
    body: SamplingPlanUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SamplingPlanOut:
    svc = SamplingService(db)
    try:
        plan = await svc.update_plan(plan_id, body)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    await db.commit()
    return _plan_out(plan)


@router.delete("/plans/{plan_id}", status_code=204, summary="Delete plan")
async def delete_plan(
    plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = SamplingService(db)
    try:
        await svc.delete_plan(plan_id)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    await db.commit()


# ── Regenerate points ────────────────────────────────────────────────────────


@router.post(
    "/plans/{plan_id}/regenerate",
    response_model=SamplingPlanOut,
    summary="Regenerate points",
)
async def regenerate_points(
    plan_id: UUID,
    body: SamplingPlanRegenerate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SamplingPlanOut:
    svc = SamplingService(db)
    try:
        plan = await svc.regenerate_points(plan_id, body)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    except FieldGeometryNotFoundError:
        raise HTTPException(404, "Field or zone geometry not found")
    await db.commit()
    return _plan_out(plan)


# ── Field collection ─────────────────────────────────────────────────────────


@router.post(
    "/plans/{plan_id}/points/{point_index}/complete",
    response_model=SamplingPlanOut,
    summary="Mark point completed",
)
async def mark_point_completed(
    plan_id: UUID,
    point_index: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    notes: str | None = None,
) -> SamplingPlanOut:
    svc = SamplingService(db)
    try:
        plan = await svc.mark_point_completed(plan_id, point_index, notes)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    await db.commit()
    return _plan_out(plan)


# ── Auto-zone from index ────────────────────────────────────────────────────


# ── Export ──────────────────────────────────────────────────────────────────


@router.get("/plans/{plan_id}/export", response_model=ExportOut, summary="Export plan")
async def export_plan(
    plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    fmt: str = Query("geojson", pattern=r"^(geojson|csv)$"),
) -> ExportOut:
    """Export sampling plan points as GeoJSON or CSV."""
    svc = SamplingService(db)
    try:
        result = await svc.export_plan(plan_id, fmt=fmt)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return ExportOut(**result)


# ── Modus work-order export ────────────────────────────────────────────────


@router.get("/plans/{plan_id}/modus-submit", summary="Export modus submit")
async def export_modus_submit(
    plan_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    lab_name: str = Query(..., description="Target lab name"),
    sample_depth: float | None = Query(None, description="Sample depth"),
    depth_unit: str = Query("inches", description="Depth unit"),
    analyses: str | None = Query(
        None, description="Comma-separated analyte names (default: standard panel)"
    ),
) -> Response:
    """Export a sampling plan as a Modus ModusSubmit XML work order.

    Returns XML that can be sent to a soil-testing laboratory.
    """
    from openfmis.services.modus import generate_modus_submit

    svc = SamplingService(db)
    try:
        plan = await svc.get_plan(plan_id)
    except SamplingPlanNotFoundError:
        raise HTTPException(404, "Sampling plan not found")

    # Extract sample points from plan's GeoJSON
    sample_points: list[dict] = []
    if plan.points_geojson and plan.points_geojson.get("coordinates"):
        for i, coord in enumerate(plan.points_geojson["coordinates"]):
            sample_points.append(
                {
                    "sample_id": f"{plan.name}-{i + 1:03d}",
                    "longitude": coord[0],
                    "latitude": coord[1],
                }
            )

    requested = None
    if analyses:
        requested = [a.strip() for a in analyses.split(",") if a.strip()]

    field_name = plan.name
    if plan.field and hasattr(plan.field, "name"):
        field_name = plan.field.name

    xml = generate_modus_submit(
        submitter_name=current_user.full_name or current_user.username,
        lab_name=lab_name,
        field_name=field_name,
        sample_points=sample_points,
        requested_analyses=requested,
        sample_depth=sample_depth,
        depth_unit=depth_unit,
    )

    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Content-Disposition": (f'attachment; filename="modus_submit_{plan.name}.xml"')},
    )
