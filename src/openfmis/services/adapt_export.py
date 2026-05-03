"""ADAPT export service — generates ADAPT-compliant JSON hierarchy."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import NotFoundError
from openfmis.models.adapt_map import ADAPTEntityMap
from openfmis.models.crop_year import CropYear
from openfmis.models.field import Field
from openfmis.models.field_event import FieldEvent
from openfmis.models.group import Group
from openfmis.models.point_dataset import PointDataset
from openfmis.models.prescription import Prescription
from openfmis.models.region import Region

# ADAPT type mappings for field event types
_EVENT_TYPE_TO_ADAPT: dict[str, str] = {
    "soil_testing": "SoilSample",
    "harvest": "HarvestObservation",
    "crop_protection": "AppliedOperation",
    "fertilizing": "AppliedOperation",
    "planting": "PlantingOperation",
    "tillage": "TillageOperation",
    "irrigation": "IrrigationOperation",
    "scouting": "CropObservation",
    "insurance": "InsuranceRecord",
}


def _adapt_type_for_event(event_type: str) -> str:
    return _EVENT_TYPE_TO_ADAPT.get(event_type, "FieldActivity")


def _build_soil_sample(base: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    """Build an ADAPT SoilSample from a soil_testing event."""
    entry = {**base, "type": "SoilSample"}
    if data:
        entries = data.get("test_entries", [])
        entry["sample_count"] = len(entries)
        # Flatten common analytes for ADAPT consumers
        analytes: list[dict[str, Any]] = []
        for te in entries:
            for key, val in te.items():
                if key in ("sample_id", "depth", "lat", "lon"):
                    continue
                analytes.append(
                    {
                        "analyte": key,
                        "value": val,
                        "unit": _soil_unit(key),
                    }
                )
        entry["analytes"] = analytes
        if entries and "depth" in entries[0]:
            entry["depth"] = entries[0]["depth"]
    return entry


def _build_harvest_observation(base: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    """Build an ADAPT HarvestObservation from a harvest event."""
    entry = {**base, "type": "HarvestObservation"}
    if data:
        for key in ("yield_value", "yield_unit", "moisture_pct", "hybrid", "crop", "area_acres"):
            if key in data:
                entry[key] = data[key]
    return entry


def _build_applied_operation(base: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    """Build an ADAPT AppliedOperation from crop_protection/fertilizing."""
    entry = {**base, "type": "AppliedOperation"}
    if data:
        products = data.get("products", [])
        entry["products"] = [
            {
                "product_name": p.get("product_name", ""),
                "rate": p.get("rate"),
                "rate_unit": p.get("rate_unit", ""),
                "total_applied": p.get("total_applied"),
            }
            for p in products
        ]
        for key in ("target_pest", "application_method", "area_acres"):
            if key in data:
                entry[key] = data[key]
    return entry


def _soil_unit(analyte: str) -> str:
    """Return the typical unit for a soil analyte."""
    if analyte == "ph":
        return ""
    if analyte.endswith("_pct"):
        return "%"
    if analyte.endswith("_ppm"):
        return "ppm"
    if analyte.endswith("_meq"):
        return "meq/100g"
    return "ppm"


class ADAPTExportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def export_group(self, group_id: uuid.UUID) -> dict[str, Any]:
        """Generate full ADAPT hierarchy for a group (Grower)."""
        result = await self.db.execute(
            select(Group).where(Group.id == group_id, Group.deleted_at.is_(None))
        )
        group = result.scalar_one_or_none()
        if group is None:
            raise NotFoundError("Group not found")

        grower_adapt_id = await self._ensure_mapping("group", group.id, "Grower")

        # Get all regions for this group
        result = await self.db.execute(
            select(Region)
            .where(Region.group_id == group_id, Region.deleted_at.is_(None))
            .order_by(Region.name)
        )
        regions = list(result.scalars().all())

        farms = []
        for region in regions:
            farm_adapt_id = await self._ensure_mapping("region", region.id, "Farm")
            farm_data = await self._build_farm(region, farm_adapt_id)
            farms.append(farm_data)

        return {
            "type": "Grower",
            "id": str(grower_adapt_id),
            "name": group.name,
            "internal_id": str(group.id),
            "farms": farms,
            "exported_at": datetime.now(UTC).isoformat(),
        }

    async def _build_farm(self, region: Region, adapt_id: uuid.UUID) -> dict[str, Any]:
        result = await self.db.execute(
            select(Field)
            .where(
                Field.region_id == region.id,
                Field.is_current.is_(True),
                Field.deleted_at.is_(None),
            )
            .order_by(Field.name)
        )
        fields = list(result.scalars().all())

        field_entries = []
        for field in fields:
            field_adapt_id = await self._ensure_mapping("field", field.id, "Field")
            field_data = await self._build_field(field, field_adapt_id)
            field_entries.append(field_data)

        return {
            "type": "Farm",
            "id": str(adapt_id),
            "name": region.name,
            "internal_id": str(region.id),
            "fields": field_entries,
        }

    async def _build_field(self, field: Field, adapt_id: uuid.UUID) -> dict[str, Any]:
        # Get crop zones
        result = await self.db.execute(
            select(CropYear)
            .where(CropYear.field_id == field.id, CropYear.deleted_at.is_(None))
            .order_by(CropYear.start_date.desc())
        )
        crop_years = list(result.scalars().all())

        crop_zones = []
        for cy in crop_years:
            cz_adapt_id = await self._ensure_mapping("crop_year", cy.id, "CropZone")
            # Get operation data (point datasets)
            ds_result = await self.db.execute(
                select(PointDataset).where(
                    PointDataset.crop_year_id == cy.id,
                    PointDataset.deleted_at.is_(None),
                )
            )
            datasets = list(ds_result.scalars().all())
            op_data = []
            for ds in datasets:
                await self._ensure_mapping("dataset", ds.id, "OperationData")
                op_data.append(
                    {
                        "type": "OperationData",
                        "dataset_type": ds.dataset_type,
                        "label": ds.label,
                        "raw_count": ds.raw_count,
                        "clean_count": ds.clean_count,
                    }
                )

            crop_zones.append(
                {
                    "type": "CropZone",
                    "id": str(cz_adapt_id),
                    "label": cy.label,
                    "start_date": cy.start_date.isoformat(),
                    "end_date": cy.end_date.isoformat(),
                    "crop_code": cy.crop_code,
                    "operation_data": op_data,
                }
            )

        # Get prescriptions
        rx_result = await self.db.execute(
            select(Prescription).where(
                Prescription.field_id == field.id,
                Prescription.deleted_at.is_(None),
            )
        )
        prescriptions = list(rx_result.scalars().all())
        rx_entries = []
        for rx in prescriptions:
            await self._ensure_mapping("prescription", rx.id, "Prescription")
            rx_entries.append(
                {
                    "type": "Prescription",
                    "name": rx.name,
                    "product": rx.product,
                    "unit": rx.unit,
                    "zone_count": rx.zone_count,
                }
            )

        # Get field events (soil tests, yield, as-applied, planting, etc.)
        ev_result = await self.db.execute(
            select(FieldEvent).where(
                FieldEvent.field_id == field.id,
                FieldEvent.is_current.is_(True),
                FieldEvent.deleted_at.is_(None),
            )
        )
        events = list(ev_result.scalars().all())
        event_entries = []
        soil_samples: list[dict[str, Any]] = []
        harvest_observations: list[dict[str, Any]] = []
        applied_operations: list[dict[str, Any]] = []

        for ev in events:
            adapt_type = _adapt_type_for_event(ev.event_type)
            await self._ensure_mapping("field_event", ev.id, adapt_type)
            entry: dict[str, Any] = {
                "type": adapt_type,
                "event_type": ev.event_type,
                "crop_year": ev.crop_year,
                "version": ev.version,
            }
            if ev.operation_date:
                entry["operation_date"] = ev.operation_date.isoformat()
            if ev.data:
                entry["data"] = ev.data
            if ev.notes:
                entry["notes"] = ev.notes

            # Route to ADAPT-specific collections
            if ev.event_type == "soil_testing":
                soil_samples.append(_build_soil_sample(entry, ev.data))
            elif ev.event_type == "harvest":
                harvest_observations.append(_build_harvest_observation(entry, ev.data))
            elif ev.event_type == "crop_protection":
                applied_operations.append(_build_applied_operation(entry, ev.data))
            else:
                event_entries.append(entry)

        return {
            "type": "Field",
            "id": str(adapt_id),
            "name": field.name,
            "internal_id": str(field.id),
            "fsa_tract": field.fsa_tract,
            "fsa_field": field.fsa_field,
            "clu_id": field.clu_id,
            "crop_zones": crop_zones,
            "prescriptions": rx_entries,
            "field_activities": event_entries,
            "soil_samples": soil_samples,
            "harvest_observations": harvest_observations,
            "applied_operations": applied_operations,
        }

    async def _ensure_mapping(
        self,
        internal_type: str,
        internal_id: uuid.UUID,
        adapt_type: str,
    ) -> uuid.UUID:
        """Get or create an ADAPT mapping, returning the ADAPT UUID."""
        result = await self.db.execute(
            select(ADAPTEntityMap).where(
                ADAPTEntityMap.internal_type == internal_type,
                ADAPTEntityMap.internal_id == internal_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing.adapt_id

        adapt_id = uuid.uuid4()
        m = ADAPTEntityMap(
            internal_type=internal_type,
            internal_id=internal_id,
            adapt_type=adapt_type,
            adapt_id=adapt_id,
        )
        self.db.add(m)
        await self.db.flush()
        return adapt_id
