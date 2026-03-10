"""Saved classification preset endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.saved_classification import (
    ClassificationCreate,
    ClassificationOut,
    ClassificationUpdate,
)
from openfmis.services.saved_classification import (
    ClassificationNotFoundError,
    SavedClassificationService,
)

router = APIRouter(prefix="/satshot/classifications", tags=["satshot-classifications"])


@router.post("/", response_model=ClassificationOut, status_code=status.HTTP_201_CREATED)
async def create_classification(
    data: ClassificationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ClassificationOut:
    svc = SavedClassificationService(db)
    try:
        record = await svc.create(current_user.id, data)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ClassificationOut.model_validate(record)


@router.get("/", response_model=list[ClassificationOut])
async def list_classifications(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    index_type: str | None = None,
) -> list[ClassificationOut]:
    svc = SavedClassificationService(db)
    records = await svc.list_for_user(current_user.id, index_type=index_type)
    return [ClassificationOut.model_validate(r) for r in records]


@router.get("/{classification_id}", response_model=ClassificationOut)
async def get_classification(
    classification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ClassificationOut:
    svc = SavedClassificationService(db)
    record = await svc.get(classification_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classification not found"
        )
    return ClassificationOut.model_validate(record)


@router.patch("/{classification_id}", response_model=ClassificationOut)
async def update_classification(
    classification_id: uuid.UUID,
    data: ClassificationUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ClassificationOut:
    svc = SavedClassificationService(db)
    try:
        record = await svc.update(classification_id, data)
        await db.commit()
    except ClassificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classification not found"
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return ClassificationOut.model_validate(record)


@router.delete("/{classification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_classification(
    classification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    svc = SavedClassificationService(db)
    try:
        await svc.delete(classification_id)
        await db.commit()
    except ClassificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Classification not found"
        )
