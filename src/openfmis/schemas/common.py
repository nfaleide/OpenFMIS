"""Shared response and pagination schemas."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str


class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)
