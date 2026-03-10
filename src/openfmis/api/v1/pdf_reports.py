"""PDF report endpoints — analysis reports and field summaries."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.database import get_db
from openfmis.dependencies import get_current_user
from openfmis.models.user import User
from openfmis.services.pdf_report import PDFReportService

router = APIRouter(prefix="/satshot/reports", tags=["satshot-reports"])


class AnalysisReportRequest(BaseModel):
    job_id: uuid.UUID
    field_name: str | None = None
    zones: list[dict] | None = None
    logo_url: str | None = None


class FieldSummaryRequest(BaseModel):
    field_id: uuid.UUID
    field_name: str | None = None


@router.post("/analysis", response_model=dict)
async def generate_analysis_report(
    data: AnalysisReportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = PDFReportService(db)
    try:
        return await svc.generate_analysis_report(
            data.job_id,
            field_name=data.field_name,
            zones=data.zones,
            logo_url=data.logo_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/analysis/html")
async def render_analysis_html(
    data: AnalysisReportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> HTMLResponse:
    svc = PDFReportService(db)
    try:
        report = await svc.generate_analysis_report(
            data.job_id,
            field_name=data.field_name,
            zones=data.zones,
            logo_url=data.logo_url,
        )
        html = await svc.render_html(report)
        return HTMLResponse(content=html)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/analysis/pdf")
async def render_analysis_pdf(
    data: AnalysisReportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Generate and download a PDF report."""
    svc = PDFReportService(db)
    try:
        report = await svc.generate_analysis_report(
            data.job_id,
            field_name=data.field_name,
            zones=data.zones,
            logo_url=data.logo_url,
        )
        html = await svc.render_html(report)
        pdf_bytes = await svc.render_pdf(html)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f"attachment; filename={report.get('index_type', 'analysis')}_report.pdf"
                )
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class EmailReportRequest(BaseModel):
    job_id: uuid.UUID
    recipient_email: str
    field_name: str | None = None
    zones: list[dict] | None = None


@router.post("/analysis/send", response_model=dict)
async def email_analysis_report(
    data: EmailReportRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Generate PDF and email it to the recipient."""
    group_id = getattr(current_user, "group_id", None)
    if not group_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User must belong to a group"
        )
    svc = PDFReportService(db)
    try:
        return await svc.generate_and_send_report(
            data.job_id,
            data.recipient_email,
            group_id,
            field_name=data.field_name,
            zones=data.zones,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/field-summary", response_model=dict)
async def generate_field_summary(
    data: FieldSummaryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    svc = PDFReportService(db)
    return await svc.generate_field_summary(data.field_id, field_name=data.field_name)
