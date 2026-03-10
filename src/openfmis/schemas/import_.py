"""Import/Export schemas."""

from uuid import UUID

from pydantic import BaseModel


class ImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]
    field_ids: list[UUID]
