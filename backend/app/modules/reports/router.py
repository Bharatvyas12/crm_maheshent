"""Reports endpoints (docs/03_API_CONTRACT.md section 15, docs/08_REPORT_SPEC.md)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.context import Ctx, parse_date, require, require_authenticated
from app.core.errors import NotFound, PermissionDenied, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.core.timeutil import business_date_of, utcnow
from app.modules.files import service as file_service
from app.modules.reports import service

router = APIRouter(tags=["reports"])


class ExportRequest(BaseModel):
    report_type: str
    format: str = "CSV"
    parameters: dict = Field(default_factory=dict)


def _range(ctx: Ctx, from_: str | None, to: str | None) -> tuple[date, date]:
    today = business_date_of(utcnow(), ctx.settings.timezone())
    from_date = parse_date(from_, "from") or today.replace(day=1)
    to_date = parse_date(to, "to") or today
    service.validate_range(ctx.settings, from_date, to_date)
    return from_date, to_date


@router.get("/reports/catalog")
async def catalog(ctx: Ctx = Depends(require_authenticated)) -> dict:
    items = [
        item
        for item in service.REPORT_CATALOG
        if item["permission"] is None or ctx.actor.has(item["permission"])
    ]
    return {"items": items, "total": len(items)}


@router.get("/reports/dashboard-summary")
async def dashboard_summary(
    as_of: str | None = Query(None), ctx: Ctx = Depends(require_authenticated)
) -> dict:
    return await service.dashboard_summary(
        ctx.session, ctx.settings, as_of=parse_date(as_of, "as_of")
    )


@router.get("/reports/attendance")
async def attendance_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    department: str | None = Query(None),
    ctx: Ctx = Depends(require("report.attendance")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.attendance_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id, department=department
    )
    return {"items": rows, "total": len(rows), "from": from_date, "to": to_date}


@router.get("/reports/work-hours")
async def work_hours_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.attendance")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.attendance_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {
        "items": [
            {
                "employee_code": row["employee_code"],
                "full_name": row["full_name"],
                "worked_seconds": row["worked_seconds"],
                "worked_hours": row["worked_hours"],
                "business_date": row["business_date"],
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.get("/reports/breaks")
async def break_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.attendance")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.break_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/overtime")
async def overtime_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.attendance")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.attendance_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {
        "items": [
            {
                "employee_code": row["employee_code"],
                "full_name": row["full_name"],
                "business_date": row["business_date"],
                "overtime_seconds": row["overtime_seconds"],
            }
            for row in rows
            if row["overtime_seconds"]
        ]
    }


@router.get("/reports/tasks")
async def task_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.tasks")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.task_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/orders")
async def order_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.orders")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.order_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/leaves")
async def leave_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.leaves")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.leave_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/advances")
async def advance_report(
    employee_id: uuid.UUID | None = Query(None), ctx: Ctx = Depends(require("report.ledger"))
) -> dict:
    rows = await service.advance_report(ctx.session, employee_id=employee_id)
    return {"items": rows, "total": len(rows)}


@router.get("/reports/ledger")
async def ledger_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.ledger")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.ledger_report(
        ctx.session, from_date=from_date, to_date=to_date, employee_id=employee_id
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/salary")
async def salary_report(
    period_year: int = Query(..., ge=2000, le=2100),
    period_month: int = Query(..., ge=1, le=12),
    employee_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.salary")),
) -> dict:
    rows = await service.salary_report(
        ctx.session,
        period_year=period_year,
        period_month=period_month,
        employee_id=employee_id,
    )
    return {"items": rows, "total": len(rows)}


@router.get("/reports/complaints")
async def complaint_report(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    status: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    ctx: Ctx = Depends(require("report.complaints")),
) -> dict:
    from_date, to_date = _range(ctx, from_, to)
    rows = await service.complaint_report(
        ctx.session, from_date=from_date, to_date=to_date, status=status, category_id=category_id
    )
    return {"items": rows, "total": len(rows)}


@router.post("/reports/exports", status_code=201)
async def create_export(
    payload: ExportRequest, ctx: Ctx = Depends(require("report.export"))
) -> dict:
    from app.modules.reports.models import ReportExport

    if payload.report_type not in service.REPORT_TYPES:
        raise ValidationError(f"Unsupported report_type: {payload.report_type}")
    formats = [fmt.upper() for fmt in (ctx.settings.json_("reports.export_formats") or ["CSV"])]
    if payload.format.upper() not in formats:
        raise ValidationError(f"Unsupported format: {payload.format}")
    row = ReportExport(
        report_type=payload.report_type,
        format=payload.format.upper(),
        parameters=payload.parameters,
        status="PENDING",
        requested_by=ctx.actor_user_id,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.audit(
        category="FILE",
        action="report.export_requested",
        entity_type="report_export",
        entity_id=row.id,
        after={"report_type": row.report_type, "format": row.format},
    )
    return _export_payload(row)


def _export_payload(row) -> dict:
    return {
        "id": row.id,
        "report_type": row.report_type,
        "format": row.format,
        "parameters": row.parameters,
        "status": row.status,
        "file_id": row.file_id,
        "row_count": row.row_count,
        "requested_by": row.requested_by,
        "requested_at": row.requested_at,
        "completed_at": row.completed_at,
        "expires_at": row.expires_at,
        "error_message": row.error_message,
    }


@router.get("/reports/exports")
async def list_exports(
    mine: bool = Query(True),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require_authenticated),
) -> dict:
    from app.modules.reports.models import ReportExport

    stmt = select(ReportExport).order_by(ReportExport.requested_at.desc())
    count_stmt = select(func.count()).select_from(ReportExport)
    if mine or not ctx.actor.has("report.export"):
        stmt = stmt.where(ReportExport.requested_by == ctx.actor_user_id)
        count_stmt = count_stmt.where(ReportExport.requested_by == ctx.actor_user_id)
    total = int((await ctx.session.execute(count_stmt)).scalar_one())
    rows = list(
        (await ctx.session.execute(stmt.offset(params.offset).limit(params.page_size))).scalars().all()
    )
    return paginated([_export_payload(row) for row in rows], total, params)


@router.get("/reports/exports/{export_id}")
async def get_export(export_id: uuid.UUID, ctx: Ctx = Depends(require_authenticated)) -> dict:
    from app.modules.reports.models import ReportExport

    row = await ctx.session.get(ReportExport, export_id)
    if row is None:
        raise NotFound("Export not found.")
    if row.requested_by != ctx.actor_user_id and not ctx.actor.has("report.export"):
        raise NotFound("Export not found.")
    return _export_payload(row)


@router.delete("/reports/exports/{export_id}", status_code=204)
async def delete_export(export_id: uuid.UUID, ctx: Ctx = Depends(require_authenticated)) -> Response:
    from app.modules.reports.models import ReportExport

    row = await ctx.session.get(ReportExport, export_id)
    if row is None:
        raise NotFound("Export not found.")
    if row.requested_by != ctx.actor_user_id and not ctx.actor.has("report.export"):
        raise NotFound("Export not found.")
    if row.file_id is not None:
        file_row = await file_service.get_file(ctx.session, row.file_id)
        await file_service.delete_file(ctx.session, file_row)
    await ctx.session.delete(row)
    await ctx.audit(
        category="FILE", action="report.export_deleted", entity_type="report_export", entity_id=export_id
    )
    return Response(status_code=204)