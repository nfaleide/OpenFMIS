"""PDFReportService — generate analysis reports as PDF.

Uses a simple HTML → PDF approach.  In production, swap the renderer
for WeasyPrint or a dedicated PDF library; the template logic stays the same.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openfmis.models.satshot import AnalysisJob

log = logging.getLogger(__name__)


class PDFReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_analysis_report(
        self,
        job_id: uuid.UUID,
        field_name: str | None = None,
        zones: list[dict] | None = None,
        logo_url: str | None = None,
    ) -> dict:
        """Generate an analysis report structure.

        Returns a dict with all data needed to render the PDF template.
        Actual PDF rendering is handled by the caller or a template engine.
        """
        job = await self._get_job(job_id)
        result = job.result or {}

        report = {
            "title": f"{job.index_type.upper()} Analysis Report",
            "generated_at": datetime.now(UTC).isoformat(),
            "field_id": str(job.field_id),
            "field_name": field_name or str(job.field_id),
            "scene_id": job.scene_id,
            "index_type": job.index_type,
            "status": job.status,
            "logo_url": logo_url,
            "statistics": {
                "mean": result.get("mean"),
                "min": result.get("min"),
                "max": result.get("max"),
                "std": result.get("std"),
                "p10": result.get("p10"),
                "p90": result.get("p90"),
                "pixel_count": result.get("pixel_count"),
                "valid_pixel_count": result.get("valid_pixel_count"),
                "nodata_fraction": result.get("nodata_fraction"),
            },
            "zones": zones or [],
            "credits_consumed": job.credits_consumed,
        }
        return report

    async def generate_field_summary(
        self,
        field_id: uuid.UUID,
        field_name: str | None = None,
    ) -> dict:
        """Generate a summary of all analyses for a field."""
        result = await self.db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.field_id == field_id, AnalysisJob.status == "complete")
            .order_by(AnalysisJob.created_at.desc())
        )
        jobs = list(result.scalars().all())

        analyses = []
        for job in jobs:
            r = job.result or {}
            analyses.append(
                {
                    "job_id": str(job.id),
                    "scene_id": job.scene_id,
                    "index_type": job.index_type,
                    "mean": r.get("mean"),
                    "min": r.get("min"),
                    "max": r.get("max"),
                    "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                }
            )

        return {
            "title": "Field Summary Report",
            "generated_at": datetime.now(UTC).isoformat(),
            "field_id": str(field_id),
            "field_name": field_name or str(field_id),
            "total_analyses": len(analyses),
            "analyses": analyses,
        }

    async def render_html(self, report: dict) -> str:
        """Render a report dict to HTML for PDF conversion."""
        stats = report.get("statistics", {})
        zones = report.get("zones", [])

        zone_rows = ""
        for z in zones:
            zone_rows += (
                f"<tr><td>{z.get('zone_name', '')}</td>"
                f"<td>{z.get('min_value', '')}</td>"
                f"<td>{z.get('max_value', '')}</td>"
                f"<td>{z.get('target_rate', '')}</td>"
                f"<td>{z.get('unit', '')}</td></tr>"
            )

        return f"""<!DOCTYPE html>
<html>
<head><title>{report.get("title", "Report")}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 40px; }}
h1 {{ color: #2c3e50; }}
table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background-color: #3498db; color: white; }}
.stat {{ display: inline-block; margin: 10px 20px; text-align: center; }}
.stat-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
.stat-label {{ font-size: 12px; color: #7f8c8d; }}
</style></head>
<body>
<h1>{report.get("title", "")}</h1>
<p>Field: {report.get("field_name", "")} | Scene: {report.get("scene_id", "")} |
   Index: {report.get("index_type", "").upper()}</p>
<p>Generated: {report.get("generated_at", "")}</p>

<h2>Statistics</h2>
<div>
  <div class="stat"><div class="stat-value">{stats.get("mean", "N/A")}</div>
  <div class="stat-label">Mean</div></div>
  <div class="stat"><div class="stat-value">{stats.get("min", "N/A")}</div>
  <div class="stat-label">Min</div></div>
  <div class="stat"><div class="stat-value">{stats.get("max", "N/A")}</div>
  <div class="stat-label">Max</div></div>
  <div class="stat"><div class="stat-value">{stats.get("std", "N/A")}</div>
  <div class="stat-label">Std Dev</div></div>
</div>

{
            "<h2>Zones</h2><table><tr><th>Zone</th><th>Min</th>"
            "<th>Max</th><th>Rate</th><th>Unit</th></tr>" + zone_rows + "</table>"
            if zone_rows
            else ""
        }
</body></html>"""

    # ── Helpers ───────────────────────────────────────────────────────────

    async def render_pdf(self, html: str) -> bytes:
        """Convert HTML to PDF bytes using WeasyPrint."""
        import weasyprint

        return weasyprint.HTML(string=html).write_pdf()

    async def generate_and_send_report(
        self,
        job_id: uuid.UUID,
        recipient_email: str,
        group_id: uuid.UUID,
        field_name: str | None = None,
        zones: list[dict] | None = None,
    ) -> dict:
        """Generate PDF report and email it via the group's delivery config."""
        from openfmis.services.email_delivery import Attachment, EmailDeliveryService

        report = await self.generate_analysis_report(
            job_id,
            field_name=field_name,
            zones=zones,
        )
        html = await self.render_html(report)
        pdf_bytes = await self.render_pdf(html)

        email_svc = EmailDeliveryService(self.db)
        result = await email_svc.send(
            group_id=group_id,
            to=recipient_email,
            subject=report["title"],
            html_body=html,
            attachments=[
                Attachment(
                    filename=f"{report.get('index_type', 'analysis')}_report.pdf",
                    content=pdf_bytes,
                    content_type="application/pdf",
                )
            ],
        )
        return {"report": report["title"], "email": result}

    async def _get_job(self, job_id: uuid.UUID) -> AnalysisJob:
        result = await self.db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job
