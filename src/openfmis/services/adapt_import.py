"""ADAPT JSON import — ingests ADAPT-compliant hierarchy into OpenFMIS.

Imports the Grower → Farm → Field → CropZone hierarchy from ADAPT JSON
(as exported by adapt_export.py or other ADAPT-compliant systems).
Creates Groups, Regions, Fields, and CropYears with ADAPT entity mappings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.models.adapt_map import ADAPTEntityMap
from openfmis.models.crop_year import CropYear
from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.region import Region

log = logging.getLogger(__name__)


@dataclass
class ADAPTImportResult:
    """Summary of an ADAPT JSON import operation."""

    groups_created: int = 0
    regions_created: int = 0
    fields_created: int = 0
    crop_years_created: int = 0
    mappings_created: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


class ADAPTImportService:
    """Imports ADAPT JSON hierarchy into OpenFMIS entities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def import_adapt_json(
        self,
        data: dict[str, Any],
        target_group_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> ADAPTImportResult:
        """Import an ADAPT JSON document.

        The document should have the structure exported by ADAPTExportService:
        ``{type: "Grower", name: ..., farms: [{type: "Farm", ...}]}``.

        Args:
            data: Parsed ADAPT JSON dict.
            target_group_id: If provided, import all farms/fields under this
                existing group instead of creating a new one from the Grower.
            created_by: User UUID for created_by fields.

        Returns:
            ADAPTImportResult with counts and warnings.
        """
        result = ADAPTImportResult()

        doc_type = data.get("type", "").lower()
        if doc_type not in ("grower", "farm", "field"):
            raise ValidationError(
                f"Unknown ADAPT document type '{data.get('type')}'. "
                f"Expected 'Grower', 'Farm', or 'Field'."
            )

        if doc_type == "grower":
            group_id = await self._import_grower(data, target_group_id, result)
            for farm in data.get("farms", []):
                await self._import_farm(farm, group_id, created_by, result)

        elif doc_type == "farm":
            if target_group_id is None:
                raise ValidationError("target_group_id required when importing a Farm document")
            await self._import_farm(data, target_group_id, created_by, result)

        elif doc_type == "field":
            if target_group_id is None:
                raise ValidationError("target_group_id required when importing a Field document")
            # Need a region — create a default one
            region = await self._get_or_create_default_region(target_group_id, result)
            await self._import_field(data, target_group_id, region.id, created_by, result)

        return result

    async def _import_grower(
        self,
        data: dict[str, Any],
        target_group_id: UUID | None,
        result: ADAPTImportResult,
    ) -> UUID:
        """Import or resolve a Grower → Group."""
        if target_group_id is not None:
            # Verify the group exists
            grp = await self.db.execute(
                select(Group).where(Group.id == target_group_id, Group.deleted_at.is_(None))
            )
            if grp.scalar_one_or_none() is None:
                raise ValidationError("Target group not found")
            return target_group_id

        name = data.get("name", "Imported Grower")
        adapt_id_str = data.get("id")

        # Check if we already have this ADAPT mapping
        if adapt_id_str:
            existing = await self._find_by_adapt_id(adapt_id_str, "Grower")
            if existing is not None:
                result.skipped += 1
                return existing

        group = Group(id=uuid4(), name=name)
        self.db.add(group)
        await self.db.flush()
        result.groups_created += 1

        if adapt_id_str:
            await self._create_mapping("group", group.id, "Grower", adapt_id_str, result)

        return group.id

    async def _import_farm(
        self,
        data: dict[str, Any],
        group_id: UUID,
        created_by: UUID | None,
        result: ADAPTImportResult,
    ) -> Region:
        """Import a Farm → Region."""
        name = data.get("name", "Imported Farm")
        adapt_id_str = data.get("id")

        # Check existing mapping
        if adapt_id_str:
            existing_id = await self._find_by_adapt_id(adapt_id_str, "Farm")
            if existing_id is not None:
                result.skipped += 1
                region_result = await self.db.execute(
                    select(Region).where(Region.id == existing_id)
                )
                region = region_result.scalar_one_or_none()
                if region is not None:
                    # Still import child fields
                    for field_data in data.get("fields", []):
                        await self._import_field(
                            field_data,
                            group_id,
                            region.id,
                            created_by,
                            result,
                        )
                    return region

        region = Region(id=uuid4(), name=name, group_id=group_id)
        self.db.add(region)
        await self.db.flush()
        result.regions_created += 1

        if adapt_id_str:
            await self._create_mapping("region", region.id, "Farm", adapt_id_str, result)

        for field_data in data.get("fields", []):
            await self._import_field(field_data, group_id, region.id, created_by, result)

        return region

    async def _import_field(
        self,
        data: dict[str, Any],
        group_id: UUID,
        region_id: UUID,
        created_by: UUID | None,
        result: ADAPTImportResult,
    ) -> Field | None:
        """Import a Field."""
        name = data.get("name")
        if not name:
            result.warnings.append("Field with no name — skipped")
            result.skipped += 1
            return None

        adapt_id_str = data.get("id")

        # Check existing mapping
        if adapt_id_str:
            existing_id = await self._find_by_adapt_id(adapt_id_str, "Field")
            if existing_id is not None:
                result.skipped += 1
                return None

        fld = Field(
            id=uuid4(),
            name=name,
            group_id=group_id,
            region_id=region_id,
            version=1,
            is_current=True,
            fsa_tract=data.get("fsa_tract"),
            fsa_field=data.get("fsa_field"),
            clu_id=data.get("clu_id"),
        )
        self.db.add(fld)
        await self.db.flush()
        result.fields_created += 1

        if adapt_id_str:
            await self._create_mapping("field", fld.id, "Field", adapt_id_str, result)

        # Import crop zones
        for cz_data in data.get("crop_zones", []):
            await self._import_crop_zone(cz_data, fld.id, result)

        return fld

    async def _import_crop_zone(
        self,
        data: dict[str, Any],
        field_id: UUID,
        result: ADAPTImportResult,
    ) -> CropYear | None:
        """Import a CropZone → CropYear."""
        label = data.get("label", "")
        adapt_id_str = data.get("id")

        if adapt_id_str:
            existing_id = await self._find_by_adapt_id(adapt_id_str, "CropZone")
            if existing_id is not None:
                result.skipped += 1
                return None

        start_date = _parse_date(data.get("start_date"))
        end_date = _parse_date(data.get("end_date"))

        if start_date is None or end_date is None:
            result.warnings.append(f"CropZone '{label}' missing dates — skipped")
            result.skipped += 1
            return None

        raw_crop_code = data.get("crop_code")
        crop_code: int | None = None
        if raw_crop_code is not None:
            try:
                crop_code = int(raw_crop_code)
            except (ValueError, TypeError):
                result.warnings.append(
                    f"CropZone '{label}' non-numeric crop_code '{raw_crop_code}' — ignored"
                )

        cy = CropYear(
            id=uuid4(),
            field_id=field_id,
            label=label,
            start_date=start_date,
            end_date=end_date,
            crop_code=crop_code,
        )
        self.db.add(cy)
        await self.db.flush()
        result.crop_years_created += 1

        if adapt_id_str:
            await self._create_mapping("crop_year", cy.id, "CropZone", adapt_id_str, result)

        return cy

    async def _get_or_create_default_region(
        self, group_id: UUID, result: ADAPTImportResult
    ) -> Region:
        """Get or create a default 'Imported' region for the group."""
        res = await self.db.execute(
            select(Region).where(
                Region.group_id == group_id,
                Region.name == "Imported",
                Region.deleted_at.is_(None),
            )
        )
        existing = res.scalar_one_or_none()
        if existing is not None:
            return existing

        region = Region(id=uuid4(), name="Imported", group_id=group_id)
        self.db.add(region)
        await self.db.flush()
        result.regions_created += 1
        return region

    async def _find_by_adapt_id(self, adapt_id_str: str, adapt_type: str) -> UUID | None:
        """Look up an internal ID by ADAPT ID."""
        try:
            adapt_id = UUID(adapt_id_str)
        except (ValueError, TypeError):
            return None

        res = await self.db.execute(
            select(ADAPTEntityMap).where(
                ADAPTEntityMap.adapt_id == adapt_id,
                ADAPTEntityMap.adapt_type == adapt_type,
            )
        )
        mapping = res.scalar_one_or_none()
        return mapping.internal_id if mapping else None

    async def _create_mapping(
        self,
        internal_type: str,
        internal_id: UUID,
        adapt_type: str,
        adapt_id_str: str,
        result: ADAPTImportResult,
    ) -> None:
        """Create an ADAPT entity mapping."""
        try:
            adapt_id = UUID(adapt_id_str)
        except (ValueError, TypeError):
            result.warnings.append(f"Invalid ADAPT ID '{adapt_id_str}' for {adapt_type}")
            return

        m = ADAPTEntityMap(
            internal_type=internal_type,
            internal_id=internal_id,
            adapt_type=adapt_type,
            adapt_id=adapt_id,
        )
        self.db.add(m)
        await self.db.flush()
        result.mappings_created += 1


def _parse_date(value: str | None) -> date | None:
    """Parse ISO date string to date."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None
