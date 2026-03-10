"""VRA prescription endpoints — TGT, FODM, BMP generation."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.schemas.vra import BMPRequest, FODMRequest, TGTRequest
from openfmis.services.vra_prescription import JobNotReadyError, VRAPrescriptionService

router = APIRouter(prefix="/satshot/prescriptions", tags=["satshot-prescriptions"])


@router.post("/tgt", response_model=dict)
async def generate_tgt(
    data: TGTRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = VRAPrescriptionService(db)
    try:
        return await svc.generate_tgt(data.job_id, [z.model_dump() for z in data.zones])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except JobNotReadyError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/fodm", response_model=dict)
async def generate_fodm(
    data: FODMRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = VRAPrescriptionService(db)
    try:
        return await svc.generate_fodm(
            data.job_id,
            data.base_rate,
            data.rate_adjustment,
            num_zones=data.num_zones,
            unit=data.unit,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except JobNotReadyError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/bmp", response_model=dict)
async def generate_bmp(
    data: BMPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = VRAPrescriptionService(db)
    try:
        return await svc.generate_bmp(
            data.job_id,
            data.breakpoints,
            data.rates,
            unit=data.unit,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except JobNotReadyError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
