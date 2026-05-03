"""Import/Export schemas."""

from uuid import UUID

from pydantic import BaseModel


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
    field_ids: list[UUID]


class ModusImportResult(BaseModel):
    events_created: int
    samples_parsed: int
    warnings: list[str]
    event_ids: list[UUID]


class SSTImportResult(BaseModel):
    groups_created: int
    regions_created: int
    fields_created: int
    mappings_created: int
    skipped: int
    warnings: list[str]


class ISOXMLImportResult(BaseModel):
    fields_created: int
    tasks_imported: int
    skipped: int
    warnings: list[str]
    field_ids: list[UUID]
