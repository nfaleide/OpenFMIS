"""Spectral index endpoints — list, create, validate custom formulas."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.spectral_index import SpectralIndexDefinition
from openfmis.models.user import User
from openfmis.services.band_math import (
    FormulaError,
    validate_formula,
)

router = APIRouter(prefix="/satshot/indices", tags=["satshot-indices"])


class IndexCreate(BaseModel):
    slug: str = Field(..., max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    display_name: str = Field(..., max_length=200)
    formula: str
    category: str = Field("custom", max_length=50)
    description: str | None = None
    parameters: dict[str, float] | None = None
    value_range: dict | None = None


class IndexUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=200)
    formula: str | None = None
    description: str | None = None
    parameters: dict[str, float] | None = None


class IndexOut(BaseModel):
    slug: str
    display_name: str
    formula: str
    required_bands: list[str]
    category: str
    description: str | None
    parameters: dict | None
    value_range: dict | None
    is_builtin: bool

    model_config = {"from_attributes": True}


class FormulaValidation(BaseModel):
    formula: str
    parameters: dict[str, float] | None = None


@router.get("/", response_model=list[IndexOut])
async def list_indices(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    category: str | None = None,
) -> list[IndexOut]:
    """List all available indices (builtins + user's custom)."""
    stmt = select(SpectralIndexDefinition)
    if category:
        stmt = stmt.where(SpectralIndexDefinition.category == category)
    result = await db.execute(stmt.order_by(SpectralIndexDefinition.slug))
    return [IndexOut.model_validate(r) for r in result.scalars().all()]


@router.get("/{slug}", response_model=IndexOut)
async def get_index(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IndexOut:
    result = await db.execute(
        select(SpectralIndexDefinition).where(SpectralIndexDefinition.slug == slug)
    )
    idx = result.scalar_one_or_none()
    if idx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index not found")
    return IndexOut.model_validate(idx)


@router.post("/", response_model=IndexOut, status_code=status.HTTP_201_CREATED)
async def create_index(
    data: IndexCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IndexOut:
    try:
        required = validate_formula(data.formula)
    except FormulaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check slug uniqueness
    existing = await db.execute(
        select(SpectralIndexDefinition).where(SpectralIndexDefinition.slug == data.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{data.slug}' already exists"
        )

    idx = SpectralIndexDefinition(
        slug=data.slug,
        display_name=data.display_name,
        formula=data.formula,
        required_bands=required,
        category=data.category,
        description=data.description,
        parameters=data.parameters,
        value_range=data.value_range,
        is_builtin=False,
        created_by=current_user.id,
        group_id=current_user.group_id if hasattr(current_user, "group_id") else None,
    )
    db.add(idx)
    await db.commit()
    await db.refresh(idx)
    return IndexOut.model_validate(idx)


@router.patch("/{slug}", response_model=IndexOut)
async def update_index(
    slug: str,
    data: IndexUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> IndexOut:
    result = await db.execute(
        select(SpectralIndexDefinition).where(SpectralIndexDefinition.slug == slug)
    )
    idx = result.scalar_one_or_none()
    if idx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index not found")
    if idx.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify builtin indices"
        )

    if data.formula is not None:
        try:
            required = validate_formula(data.formula)
        except FormulaError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        idx.formula = data.formula
        idx.required_bands = required
    if data.display_name is not None:
        idx.display_name = data.display_name
    if data.description is not None:
        idx.description = data.description
    if data.parameters is not None:
        idx.parameters = data.parameters

    await db.commit()
    await db.refresh(idx)
    return IndexOut.model_validate(idx)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_index(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    result = await db.execute(
        select(SpectralIndexDefinition).where(SpectralIndexDefinition.slug == slug)
    )
    idx = result.scalar_one_or_none()
    if idx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index not found")
    if idx.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete builtin indices"
        )
    await db.delete(idx)
    await db.commit()


@router.post("/validate", response_model=dict)
async def validate_formula_endpoint(
    data: FormulaValidation,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Validate a formula without saving it."""
    try:
        required = validate_formula(data.formula)
    except FormulaError as e:
        return {"valid": False, "error": str(e)}
    return {"valid": True, "required_bands": required}
