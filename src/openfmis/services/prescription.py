"""Prescription + InterpolationSurface services."""

import json
from uuid import UUID

from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.prescription import InterpolationSurface, Prescription
from openfmis.schemas.prescription import (
    InterpolationSurfaceCreate,
    PrescriptionCreate,
    PrescriptionUpdate,
)


class InterpolationSurfaceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, surface_id: UUID) -> InterpolationSurface:
        result = await self.db.execute(
            select(InterpolationSurface).where(InterpolationSurface.id == surface_id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            raise NotFoundError("Interpolation surface not found")
        return s

    async def list_by_field(self, field_id: UUID) -> list[InterpolationSurface]:
        result = await self.db.execute(
            select(InterpolationSurface)
            .where(InterpolationSurface.field_id == field_id)
            .order_by(InterpolationSurface.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(self, data: InterpolationSurfaceCreate) -> InterpolationSurface:
        s = InterpolationSurface(
            dataset_id=data.dataset_id,
            field_id=data.field_id,
            method=data.method,
            cell_size_m=data.cell_size_m,
            parameters=data.parameters,
            layer_ref=data.layer_ref,
        )
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return s


class PrescriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, prescription_id: UUID) -> Prescription:
        result = await self.db.execute(
            select(Prescription).where(
                Prescription.id == prescription_id, Prescription.deleted_at.is_(None)
            )
        )
        p = result.scalar_one_or_none()
        if p is None:
            raise NotFoundError("Prescription not found")
        return p

    async def list_prescriptions(
        self,
        field_id: UUID | None = None,
        crop_year_id: UUID | None = None,
    ) -> list[Prescription]:
        query = select(Prescription).where(Prescription.deleted_at.is_(None))
        if field_id is not None:
            query = query.where(Prescription.field_id == field_id)
        if crop_year_id is not None:
            query = query.where(Prescription.crop_year_id == crop_year_id)
        query = query.order_by(Prescription.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, data: PrescriptionCreate) -> Prescription:
        p = Prescription(
            field_id=data.field_id,
            crop_year_id=data.crop_year_id,
            name=data.name,
            product=data.product,
            unit=data.unit,
            zone_count=data.zone_count,
            classification=data.classification,
            zones=data.zones,
            source_surface_id=data.source_surface_id,
            rec_model=data.rec_model,
            export_formats=data.export_formats,
            notes=data.notes,
        )
        if data.geometry_geojson is not None:
            p.geometry = func.ST_SetSRID(
                func.ST_GeomFromGeoJSON(json.dumps(data.geometry_geojson)),
                4326,
            )
        self.db.add(p)
        await self.db.flush()
        await self.db.refresh(p)
        return p

    async def update(self, prescription_id: UUID, data: PrescriptionUpdate) -> Prescription:
        p = await self.get_by_id(prescription_id)
        update_data = data.model_dump(exclude_unset=True)
        geojson = update_data.pop("geometry_geojson", None)
        for attr, value in update_data.items():
            setattr(p, attr, value)
        if geojson is not None:
            p.geometry = func.ST_SetSRID(
                func.ST_GeomFromGeoJSON(json.dumps(geojson)),
                4326,
            )
        await self.db.flush()
        await self.db.refresh(p)
        return p

    async def soft_delete(self, prescription_id: UUID) -> None:
        from datetime import UTC, datetime

        p = await self.get_by_id(prescription_id)
        p.deleted_at = datetime.now(UTC)
        await self.db.flush()

    async def get_geometry_geojson(self, prescription_id: UUID) -> dict | None:
        result = await self.db.execute(
            select(ST_AsGeoJSON(Prescription.geometry)).where(Prescription.id == prescription_id)
        )
        geojson_str = result.scalar_one_or_none()
        if geojson_str is None:
            return None
        return json.loads(geojson_str)
