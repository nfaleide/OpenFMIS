"""SST Package parser — imports Satshot .sst project archives into OpenFMIS.

An SST package is a ZIP archive containing:
  - ``dtumeta.mdb`` — MS Access database with Client/Farm/Field/FileInfo tables
  - Shapefiles (.shp + companions) — field boundary geometry

The parser extracts the hierarchy (Client → Farm → Field) and reads boundary
geometries from embedded shapefiles via fiona.  MDB parsing uses the
``mdb-export`` command-line tool (mdbtools package).
"""

from __future__ import annotations

import csv
import io
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import fiona
from shapely.geometry import mapping as shapely_mapping
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union
from shapely.validation import make_valid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.exceptions import ValidationError
from openfmis.models.adapt_map import ADAPTEntityMap
from openfmis.models.field import Field
from openfmis.models.group import Group
from openfmis.models.region import Region

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SSTClient:
    """Parsed Client (Grower) from SST package."""

    clientid: str
    name: str
    raw: dict[str, str] = field(default_factory=dict)
    farms: list[SSTFarm] = field(default_factory=list)


@dataclass
class SSTFarm:
    """Parsed Farm from SST package."""

    farmid: str
    clientid: str
    name: str
    raw: dict[str, str] = field(default_factory=dict)
    fields: list[SSTField] = field(default_factory=list)


@dataclass
class SSTField:
    """Parsed Field from SST package."""

    fieldid: str
    farmid: str
    name: str
    boundary_geojson: dict[str, Any] | None = None
    raw: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SSTPackageData:
    """Complete parsed SST package."""

    clients: list[SSTClient] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SSTImportResult:
    """Summary of an SST package import."""

    groups_created: int = 0
    regions_created: int = 0
    fields_created: int = 0
    mappings_created: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

# Columns to exclude from Client rows (internal SST metadata)
_CLIENT_SKIP_COLS = {"project", "checkedout", "archive", "archivesrc"}


def _clean_uuid(val: str) -> str:
    """Strip braces from SST UUIDs like ``{12345678-...}``."""
    return val.strip().strip("{}")


def _mdb_export_table(mdb_path: str, table: str) -> list[dict[str, str]]:
    """Export a table from an MDB file using mdb-export.

    Returns a list of dicts (one per row), with column names lower-cased.
    """
    try:
        proc = subprocess.run(
            ["mdb-export", "-d", "|", mdb_path, table],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise ValidationError(
            "mdb-export not found. Install mdbtools: "
            "brew install mdbtools (macOS) or apt install mdbtools (Linux)"
        )

    if proc.returncode != 0:
        log.warning("mdb-export %s failed: %s", table, proc.stderr.strip())
        return []

    reader = csv.DictReader(io.StringIO(proc.stdout), delimiter="|")
    rows: list[dict[str, str]] = []
    for row in reader:
        rows.append({k.lower().strip(): v.strip() for k, v in row.items()})
    return rows


def _read_shapefiles_from_dir(
    base_dir: str,
    field_shp_map: dict[str, str],
) -> dict[str, dict[str, Any] | None]:
    """Read shapefile geometries for each field ID.

    Args:
        base_dir: Root extraction directory.
        field_shp_map: Mapping of fieldid → relative shapefile path.

    Returns:
        fieldid → GeoJSON geometry dict (or None on failure).
    """
    result: dict[str, dict[str, Any] | None] = {}

    for fieldid, rel_path in field_shp_map.items():
        shp_path = os.path.join(base_dir, rel_path)
        if not os.path.exists(shp_path):
            # Try case-insensitive search
            shp_path = _find_file_ci(base_dir, rel_path)

        if shp_path is None or not os.path.exists(shp_path):
            log.warning("Shapefile not found for field %s: %s", fieldid, rel_path)
            result[fieldid] = None
            continue

        try:
            geoms = []
            with fiona.open(shp_path) as src:
                for feat in src:
                    geom = shapely_shape(feat["geometry"])
                    if not geom.is_valid:
                        geom = make_valid(geom)
                    if not geom.is_empty:
                        geoms.append(geom)

            if not geoms:
                result[fieldid] = None
                continue

            unified = unary_union(geoms)
            # Ensure MultiPolygon
            if unified.geom_type == "Polygon":
                from shapely.geometry import MultiPolygon

                unified = MultiPolygon([unified])
            elif unified.geom_type != "MultiPolygon":
                log.warning("Unexpected geometry type %s for field %s", unified.geom_type, fieldid)
                result[fieldid] = None
                continue

            result[fieldid] = shapely_mapping(unified)

        except Exception as exc:
            log.warning("Error reading shapefile for field %s: %s", fieldid, exc)
            result[fieldid] = None

    return result


def _find_file_ci(base_dir: str, rel_path: str) -> str | None:
    """Case-insensitive file search."""
    target = rel_path.lower().replace("\\", "/")
    for root, _dirs, files in os.walk(base_dir):
        for f in files:
            full = os.path.join(root, f)
            relative = os.path.relpath(full, base_dir).replace("\\", "/")
            if relative.lower() == target:
                return full
    return None


def parse_sst_package(file_content: bytes) -> SSTPackageData:
    """Parse an SST package ZIP archive.

    Args:
        file_content: Raw bytes of the .sst ZIP file.

    Returns:
        SSTPackageData with parsed hierarchy and boundary geometries.

    Raises:
        ValidationError: If the file is not a valid ZIP or missing dtumeta.mdb.
    """
    result = SSTPackageData()

    if not zipfile.is_zipfile(io.BytesIO(file_content)):
        raise ValidationError("File is not a valid ZIP archive")

    tmpdir = tempfile.mkdtemp(prefix="sst_")
    try:
        # Extract ZIP
        with zipfile.ZipFile(io.BytesIO(file_content)) as zf:
            zf.extractall(tmpdir)

        # Find dtumeta.mdb (case-insensitive)
        mdb_path = _find_file_ci(tmpdir, "dtumeta.mdb")
        if mdb_path is None:
            raise ValidationError("SST package missing dtumeta.mdb")

        # Parse tables
        clients_raw = _mdb_export_table(mdb_path, "Client")
        farms_raw = _mdb_export_table(mdb_path, "Farm")
        fields_raw = _mdb_export_table(mdb_path, "Field")
        fileinfo_raw = _mdb_export_table(mdb_path, "FileInfo")

        # Build field → shapefile map from FileInfo
        # FileInfo has: relpath, filetype, etc. We want filetype="Field Boundary"
        field_shp_map: dict[str, str] = {}
        for fi in fileinfo_raw:
            ftype = fi.get("filetype", "").strip()
            relpath = fi.get("relpath", "").strip()
            if ftype.lower() == "field boundary" and relpath.lower().endswith(".shp"):
                # relpath format: "Fields\{fieldid}\filename.shp"
                parts = relpath.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    fid = _clean_uuid(parts[1])
                    field_shp_map[fid] = relpath.replace("\\", "/")

        # Read boundary geometries
        geometries = _read_shapefiles_from_dir(tmpdir, field_shp_map)

        # Index farms and fields by parent
        farms_by_client: dict[str, list[dict]] = {}
        for f in farms_raw:
            cid = _clean_uuid(f.get("clientid", ""))
            farms_by_client.setdefault(cid, []).append(f)

        fields_by_farm: dict[str, list[dict]] = {}
        for f in fields_raw:
            fid = _clean_uuid(f.get("farmid", ""))
            fields_by_farm.setdefault(fid, []).append(f)

        # Build hierarchy
        for c in clients_raw:
            clientid = _clean_uuid(c.get("clientid", ""))
            if not clientid:
                result.warnings.append("Client row with no clientid — skipped")
                continue

            client = SSTClient(
                clientid=clientid,
                name=c.get("group", c.get("name", "Unknown Client")),
                raw={k: v for k, v in c.items() if k not in _CLIENT_SKIP_COLS},
            )

            for fm in farms_by_client.get(clientid, []):
                farmid = _clean_uuid(fm.get("farmid", ""))
                if not farmid:
                    result.warnings.append("Farm row with no farmid — skipped")
                    continue

                farm = SSTFarm(
                    farmid=farmid,
                    clientid=clientid,
                    name=fm.get("group", fm.get("name", "Unknown Farm")),
                    raw=fm,
                )

                for fd in fields_by_farm.get(farmid, []):
                    fieldid = _clean_uuid(fd.get("fieldid", ""))
                    if not fieldid:
                        result.warnings.append("Field row with no fieldid — skipped")
                        continue

                    sst_field = SSTField(
                        fieldid=fieldid,
                        farmid=farmid,
                        name=fd.get("group", fd.get("name", "Unknown Field")),
                        boundary_geojson=geometries.get(fieldid),
                        raw=fd,
                    )
                    if fieldid in field_shp_map and geometries.get(fieldid) is None:
                        sst_field.warnings.append("Boundary shapefile could not be read")

                    farm.fields.append(sst_field)

                client.farms.append(farm)

            result.clients.append(client)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return result


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class SSTImportService:
    """Imports parsed SST package data into OpenFMIS entities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def import_sst_package(
        self,
        data: SSTPackageData,
        target_group_id: UUID | None = None,
        created_by: UUID | None = None,
    ) -> SSTImportResult:
        """Import parsed SST data into OpenFMIS.

        Args:
            data: Parsed SST package data.
            target_group_id: If set, import all clients' farms under this
                existing group instead of creating new groups.
            created_by: User UUID for audit fields.

        Returns:
            SSTImportResult with counts and warnings.
        """
        result = SSTImportResult()
        result.warnings.extend(data.warnings)

        for client in data.clients:
            group_id = await self._import_client(client, target_group_id, result)
            for farm in client.farms:
                region = await self._import_farm(farm, group_id, result)
                for fld in farm.fields:
                    await self._import_field(fld, group_id, region.id, result)

        return result

    async def _import_client(
        self,
        client: SSTClient,
        target_group_id: UUID | None,
        result: SSTImportResult,
    ) -> UUID:
        """Import Client → Group."""
        if target_group_id is not None:
            grp = await self.db.execute(
                select(Group).where(Group.id == target_group_id, Group.deleted_at.is_(None))
            )
            if grp.scalar_one_or_none() is None:
                raise ValidationError("Target group not found")
            return target_group_id

        # Check existing mapping by SST clientid
        existing = await self._find_by_sst_id(client.clientid, "SSTClient")
        if existing is not None:
            result.skipped += 1
            return existing

        group = Group(id=uuid4(), name=client.name)
        self.db.add(group)
        await self.db.flush()
        result.groups_created += 1

        await self._create_mapping("group", group.id, "SSTClient", client.clientid, result)
        return group.id

    async def _import_farm(
        self,
        farm: SSTFarm,
        group_id: UUID,
        result: SSTImportResult,
    ) -> Region:
        """Import Farm → Region."""
        existing_id = await self._find_by_sst_id(farm.farmid, "SSTFarm")
        if existing_id is not None:
            result.skipped += 1
            res = await self.db.execute(select(Region).where(Region.id == existing_id))
            region = res.scalar_one_or_none()
            if region is not None:
                return region

        region = Region(id=uuid4(), name=farm.name, group_id=group_id)
        self.db.add(region)
        await self.db.flush()
        result.regions_created += 1

        await self._create_mapping("region", region.id, "SSTFarm", farm.farmid, result)
        return region

    async def _import_field(
        self,
        sst_field: SSTField,
        group_id: UUID,
        region_id: UUID,
        result: SSTImportResult,
    ) -> Field | None:
        """Import SST Field → OpenFMIS Field."""
        if not sst_field.name:
            result.warnings.append("Field with no name — skipped")
            result.skipped += 1
            return None

        existing_id = await self._find_by_sst_id(sst_field.fieldid, "SSTField")
        if existing_id is not None:
            result.skipped += 1
            return None

        geom_wkt = None
        if sst_field.boundary_geojson is not None:
            geom = shapely_shape(sst_field.boundary_geojson)
            geom_wkt = geom.wkt

        fld = Field(
            id=uuid4(),
            name=sst_field.name,
            group_id=group_id,
            region_id=region_id,
            version=1,
            is_current=True,
            geometry=f"SRID=4326;{geom_wkt}" if geom_wkt else None,
        )
        self.db.add(fld)
        await self.db.flush()
        result.fields_created += 1

        await self._create_mapping("field", fld.id, "SSTField", sst_field.fieldid, result)

        if sst_field.warnings:
            result.warnings.extend(f"Field '{sst_field.name}': {w}" for w in sst_field.warnings)

        return fld

    async def _find_by_sst_id(self, sst_id: str, sst_type: str) -> UUID | None:
        """Look up internal ID by SST UUID."""
        try:
            adapt_id = UUID(sst_id)
        except (ValueError, TypeError):
            return None

        res = await self.db.execute(
            select(ADAPTEntityMap).where(
                ADAPTEntityMap.adapt_id == adapt_id,
                ADAPTEntityMap.adapt_type == sst_type,
            )
        )
        mapping = res.scalar_one_or_none()
        return mapping.internal_id if mapping else None

    async def _create_mapping(
        self,
        internal_type: str,
        internal_id: UUID,
        sst_type: str,
        sst_id: str,
        result: SSTImportResult,
    ) -> None:
        """Create an entity mapping for an SST UUID."""
        try:
            adapt_id = UUID(sst_id)
        except (ValueError, TypeError):
            result.warnings.append(f"Invalid SST UUID '{sst_id}' for {sst_type}")
            return

        m = ADAPTEntityMap(
            internal_type=internal_type,
            internal_id=internal_id,
            adapt_type=sst_type,
            adapt_id=adapt_id,
        )
        self.db.add(m)
        await self.db.flush()
        result.mappings_created += 1
