"""Import endpoints — vector file, Modus XML, and SST package ingestion."""

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user, verify_group_access
from openfmis.exceptions import ValidationError
from openfmis.models.field_event import EventType
from openfmis.models.user import User
from openfmis.schemas.field_event import FieldEventCreate
from openfmis.schemas.import_ import (
    ImportResult,
    ISOXMLImportResult,
    ModusImportResult,
    SSTImportResult,
)
from openfmis.services.field_event import FieldEventService
from openfmis.services.import_ import ImportService
from openfmis.services.isoxml import isoxml_to_field_data, parse_isoxml
from openfmis.services.modus import ModusParseError, modus_to_soil_event_data, parse_modus_xml
from openfmis.services.sst_package import SSTImportService, parse_sst_package

router = APIRouter(prefix="/import", tags=["import"])

# 50 MB upload limit
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post("/vector", response_model=ImportResult, status_code=200, summary="Import vector")
async def import_vector(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Shapefile (.zip), GeoJSON, KML, or CSV")],
    group_id: Annotated[UUID, Form(description="Group that will own the imported fields")],
    region_id: Annotated[UUID, Form(description="Region (farm) the imported fields belong to")],
    name_field: Annotated[
        str | None,
        Form(description="Attribute name to use as the field name (auto-detected if omitted)"),
    ] = None,
) -> ImportResult:
    """Import vector geometries from a file and create Field records.

    Accepted formats:
    - **Shapefile** — zip archive containing .shp/.dbf/.shx (+ optional .prj)
    - **GeoJSON** — .geojson or .json
    - **KML** — .kml
    - **CSV** — with a `wkt` column or `lat`/`lon` columns

    Returns a summary of created fields, skipped features, and any per-feature errors.
    """
    if file.filename is None:
        raise ValidationError("File must have a filename.")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    await verify_group_access(current_user, group_id)

    svc = ImportService(db)
    return await svc.import_vector(
        file_content=content,
        filename=file.filename,
        group_id=group_id,
        region_id=region_id,
        created_by=current_user.id,
        name_field=name_field,
    )


@router.post("/modus", response_model=ModusImportResult, status_code=200, summary="Import modus")
async def import_modus(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Modus XML soil test results file")],
    field_id: Annotated[UUID, Form(description="Field these soil samples belong to")],
    crop_year: Annotated[
        int, Form(description="Crop year for the soil test events", ge=1900, le=2100)
    ],
) -> ModusImportResult:
    """Import soil test results from a Modus (AgGateway) XML file.

    Parses the XML, extracts sample data, and creates FieldEvent records
    of type ``soil_testing`` for the specified field and crop year.
    Each sample in the file becomes one FieldEvent.
    """
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    try:
        parse_result = parse_modus_xml(content)
    except ModusParseError as exc:
        raise ValidationError(str(exc)) from exc

    soil_events = modus_to_soil_event_data(parse_result)
    if not soil_events:
        return ModusImportResult(
            events_created=0,
            samples_parsed=parse_result.sample_count,
            warnings=parse_result.warnings or ["No usable soil test data found"],
            event_ids=[],
        )

    event_svc = FieldEventService(db)
    event_ids = []
    for soil_data in soil_events:
        event = await event_svc.create_event(
            FieldEventCreate(
                field_id=field_id,
                event_type=EventType.SOIL_TESTING,
                crop_year=crop_year,
                operation_date=soil_data.sample_date,
                data=soil_data.model_dump(mode="json"),
            ),
            created_by=current_user.id,
        )
        event_ids.append(event.id)

    return ModusImportResult(
        events_created=len(event_ids),
        samples_parsed=parse_result.sample_count,
        warnings=parse_result.warnings,
        event_ids=event_ids,
    )


@router.post(
    "/sst-package",
    response_model=SSTImportResult,
    status_code=200,
    summary="Import sst package",
)
async def import_sst_package(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="SST package (.sst ZIP archive)")],
    target_group_id: Annotated[
        UUID | None,
        Form(description="Import all farms/fields under this existing group"),
    ] = None,
) -> SSTImportResult:
    """Import a Satshot SST package (.sst ZIP archive).

    Parses the MDB metadata and embedded shapefiles, creating groups,
    regions, and fields with boundary geometry.  Requires ``mdb-export``
    (mdbtools) on the server.
    """
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    if target_group_id is not None:
        await verify_group_access(current_user, target_group_id)

    try:
        package_data = parse_sst_package(content)
    except ValidationError:
        raise

    svc = SSTImportService(db)
    result = await svc.import_sst_package(
        package_data,
        target_group_id=target_group_id,
        created_by=current_user.id,
    )

    return SSTImportResult(
        groups_created=result.groups_created,
        regions_created=result.regions_created,
        fields_created=result.fields_created,
        mappings_created=result.mappings_created,
        skipped=result.skipped,
        warnings=result.warnings,
    )


@router.post("/isoxml", response_model=ISOXMLImportResult, status_code=200, summary="Import isoxml")
async def import_isoxml(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    file: Annotated[
        UploadFile,
        File(description="ISOXML file (.xml or .zip with TASKDATA.XML)"),
    ],
    group_id: Annotated[UUID, Form(description="Group that will own imported fields")],
    region_id: Annotated[UUID, Form(description="Region for imported fields")],
) -> ISOXMLImportResult:
    """Import field boundaries and task data from ISOXML (ISO 11783-10).

    Accepts a TASKDATA.XML file or a ZIP archive containing one.
    Creates Field records from Partfield elements with polygon geometry.
    """
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File too large. Maximum size is {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )

    await verify_group_access(current_user, group_id)

    try:
        isoxml_data = parse_isoxml(content)
    except ValidationError:
        raise

    field_dicts = isoxml_to_field_data(isoxml_data)
    warnings = list(isoxml_data.warnings)
    field_ids: list[UUID] = []
    skipped = 0

    for fd in field_dicts:
        try:
            from json import dumps

            from sqlalchemy import func

            from openfmis.models.field import Field as FieldModel

            fld = FieldModel(
                id=uuid4(),
                name=fd["name"],
                group_id=group_id,
                region_id=region_id,
                version=1,
                is_current=True,
            )
            geojson_str = dumps(fd["geometry_geojson"])
            fld.geometry = func.ST_SetSRID(
                func.ST_Multi(func.ST_GeomFromGeoJSON(geojson_str)),
                4326,
            )
            db.add(fld)
            await db.flush()
            field_ids.append(fld.id)
        except Exception as exc:
            warnings.append(f"Field '{fd['name']}': {exc}")
            skipped += 1

    return ISOXMLImportResult(
        fields_created=len(field_ids),
        tasks_imported=len(isoxml_data.tasks),
        skipped=skipped,
        warnings=warnings,
        field_ids=field_ids,
    )
