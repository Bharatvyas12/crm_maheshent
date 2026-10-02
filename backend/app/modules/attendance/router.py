"""Attendance endpoints (docs/03_API_CONTRACT.md section 4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.context import Ctx, get_ctx, parse_date, parse_datetime, require, require_any
from app.api.idempotency import begin_idempotency, finish_idempotency, replay_response
from app.core.errors import Conflict, NotFound, RuleViolation, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.core.timeutil import business_date_of, utcnow
from app.modules.attendance import service
from app.modules.attendance.models import BreakType, BusinessHoliday
from app.modules.directory import service as directory_service

router = APIRouter(tags=["attendance"])


class EvidenceRequest(BaseModel):
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    accuracy_meters: Decimal | None = Field(default=None, ge=0)
    location_captured_at: datetime | None = None
    qr_token: str | None = Field(default=None, max_length=512)
    client_time: datetime | None = None
    device_info: dict | None = None


class BreakStartRequest(BaseModel):
    break_type_id: uuid.UUID


class BreakTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    is_paid: bool = False
    max_minutes: int | None = Field(default=None, ge=1, le=1440)
    requires_approval: bool = False
    counts_toward_max_per_day: bool = True


class BreakTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_paid: bool | None = None
    max_minutes: int | None = Field(default=None, ge=1, le=1440)
    requires_approval: bool | None = None
    counts_toward_max_per_day: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class HolidayCreate(BaseModel):
    holiday_date: date
    name: str = Field(min_length=1, max_length=200)
    is_paid: bool = True
    is_working_day: bool = False
    notes: str | None = Field(default=None, max_length=500)


class QrIssueRequest(BaseModel):
    purpose: str = Field(default="SHOP_CHECKIN")


class RecomputeRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CorrectionCreate(BaseModel):
    attendance_record_id: uuid.UUID
    correction_type: str
    requested_check_in_at: datetime | None = None
    requested_check_out_at: datetime | None = None
    requested_break_start_at: datetime | None = None
    requested_break_end_at: datetime | None = None
    requested_notes: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=1, max_length=500)
    attachment_file_id: uuid.UUID | None = None


class CorrectionDecision(BaseModel):
    decision_notes: str | None = Field(default=None, max_length=1000)
    adjust_to: dict | None = None


class CorrectionReject(BaseModel):
    decision_notes: str = Field(min_length=1, max_length=1000)


class CorrectionCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def _gps(payload: EvidenceRequest) -> service.GpsEvidence:
    return service.GpsEvidence(
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        location_captured_at=payload.location_captured_at,
    )


async def _employee(ctx: Ctx):
    return await directory_service.get_employee(ctx.session, ctx.employee_id)


@router.get("/attendance/me/today")
async def today(ctx: Ctx = Depends(require("attendance.read.self"))) -> dict:
    business_date = business_date_of(utcnow(), ctx.settings.timezone())
    record = await service.find_record(ctx.session, ctx.employee_id, business_date)
    if record is None:
        placeholder = {
            "id": None,
            "employee_id": ctx.employee_id,
            "business_date": business_date,
            "status": "NOT_MARKED",
            "day_classification": "NONE",
            "first_check_in_at": None,
            "last_check_out_at": None,
            "worked_seconds": 0,
            "worked_hours": "0.00",
            "break_seconds": 0,
            "unpaid_break_seconds": 0,
            "overtime_seconds": 0,
            "late_minutes": 0,
            "early_checkout_minutes": 0,
            "is_open": False,
            "is_corrected": False,
            "computed_at": None,
            "version": 0,
            "next_allowed_action": "CHECK_IN",
        }
        return placeholder
    open_session = await service.find_open_session(ctx.session, ctx.employee_id)
    open_break = await service.find_open_break(ctx.session, record.id)
    return service.serialize_record(record, has_open_break=bool(open_break), has_session=bool(open_session))


@router.post("/attendance/check-in", status_code=201)
async def check_in(
    payload: EvidenceRequest, request: Request, ctx: Ctx = Depends(require("attendance.checkin.self"))
) -> Response:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="attendance.check-in", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    employee = await _employee(ctx)
    record, verification = await service.check_in(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        gps=_gps(payload),
        qr_payload=payload.qr_token,
        source="WEB",
        actor_user_id=ctx.actor_user_id,
        meta=ctx.meta,
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.checked_in",
        entity_type="attendance_record",
        entity_id=record.id,
        after={"worked_seconds": record.worked_seconds},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.checked_in.v1",
        aggregate_type="attendance_record",
        aggregate_id=record.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = {**service.serialize_record(record, has_session=True), "verification": verification}
    await finish_idempotency(guard, 201, body)
    return JSONResponse(status_code=201, content=_jsonable(body))


def _jsonable(value):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(value)


@router.post("/attendance/check-out")
async def check_out(
    payload: EvidenceRequest, request: Request, ctx: Ctx = Depends(require("attendance.checkout.self"))
) -> Response:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="attendance.check-out", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    employee = await _employee(ctx)
    record, verification = await service.check_out(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        gps=_gps(payload),
        qr_payload=payload.qr_token,
        source="WEB",
        actor_user_id=ctx.actor_user_id,
        meta=ctx.meta,
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.checked_out",
        entity_type="attendance_record",
        entity_id=record.id,
        after={"worked_seconds": record.worked_seconds},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.checked_out.v1",
        aggregate_type="attendance_record",
        aggregate_id=record.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = {**service.serialize_record(record), "verification": verification}
    await finish_idempotency(guard, 200, body)
    return JSONResponse(status_code=200, content=_jsonable(body))


@router.post("/attendance/break/start", status_code=201)
async def break_start(
    payload: BreakStartRequest, request: Request, ctx: Ctx = Depends(require("attendance.break.self"))
) -> Response:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="attendance.break.start", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    employee = await _employee(ctx)
    row, break_type, _record = await service.break_start(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        break_type_id=payload.break_type_id,
        source="WEB",
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.break_started",
        entity_type="break_session",
        entity_id=row.id,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.break_started.v1",
        aggregate_type="break_session",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = service.serialize_break(row, break_type)
    await finish_idempotency(guard, 201, body)
    return JSONResponse(status_code=201, content=_jsonable(body))


@router.post("/attendance/break/end")
async def break_end(
    request: Request, ctx: Ctx = Depends(require("attendance.break.self"))
) -> Response:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="attendance.break.end", payload={}
    )
    if replay is not None:
        return replay_response(replay)
    employee = await _employee(ctx)
    row, break_type, _record = await service.break_end(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        source="WEB",
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.break_ended",
        entity_type="break_session",
        entity_id=row.id,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.break_ended.v1",
        aggregate_type="break_session",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = service.serialize_break(row, break_type)
    await finish_idempotency(guard, 200, body)
    return JSONResponse(status_code=200, content=_jsonable(body))

@router.get("/attendance/me")
async def my_attendance(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("attendance.read.self")),
) -> dict:
    from_date = parse_date(from_, "from")
    to_date = parse_date(to, "to")
    rows, total = await service.query_records(
        ctx.session,
        employee_ids=[ctx.employee_id],
        from_date=from_date,
        to_date=to_date,
        offset=params.offset,
        limit=params.page_size,
    )
    open_session = await service.find_open_session(ctx.session, ctx.employee_id)
    items = []
    for row in rows:
        open_break = await service.find_open_break(ctx.session, row.id)
        items.append(service.serialize_record(row, has_open_break=bool(open_break), has_session=bool(open_session)))
    return paginated(items, total, params)


@router.get("/attendance/me/summary")
async def my_summary(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    ctx: Ctx = Depends(require("attendance.read.self")),
) -> dict:
    today = business_date_of(utcnow(), ctx.settings.timezone())
    from_date = parse_date(from_, "from") or today.replace(day=1)
    to_date = parse_date(to, "to") or today
    if from_date > to_date:
        raise ValidationError("from must not be after to.")
    return await service.attendance_summary(
        ctx.session, employee_id=ctx.employee_id, from_date=from_date, to_date=to_date
    )


@router.get("/attendance")
async def list_attendance(
    employee_id: uuid.UUID | None = Query(None),
    department: str | None = Query(None),
    status: str | None = Query(None),
    day_classification: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("attendance.read.all")),
) -> dict:
    rows, total = await service.query_records(
        ctx.session,
        employee_ids=[employee_id] if employee_id else None,
        status=status,
        day_classification=day_classification,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        department=department,
        q=q,
        offset=params.offset,
        limit=params.page_size,
    )
    items = [service.serialize_record(row) for row in rows]
    return paginated(items, total, params)


@router.get("/attendance/{record_id}")
async def get_record(record_id: uuid.UUID, ctx: Ctx = Depends(require("attendance.read.self"))) -> dict:
    record = await service.get_record_by_id(ctx.session, record_id)
    if record.employee_id != ctx.employee_id and not ctx.actor.has("attendance.read.all"):
        raise NotFound("Attendance record not found.")
    open_break = await service.find_open_break(ctx.session, record.id)
    open_session = await service.find_open_session(ctx.session, record.employee_id)
    return service.serialize_record(record, has_open_break=bool(open_break), has_session=bool(open_session))


@router.get("/attendance/{record_id}/events")
async def get_record_events(record_id: uuid.UUID, ctx: Ctx = Depends(require("attendance.read.self"))) -> dict:
    record = await service.get_record_by_id(ctx.session, record_id)
    if record.employee_id != ctx.employee_id and not ctx.actor.has("attendance.read.all"):
        raise NotFound("Attendance record not found.")
    rows = await service.list_events(ctx.session, record.id)
    return {"items": [service.serialize_event(row) for row in rows]}


@router.get("/attendance/{record_id}/verifications")
async def get_record_verifications(
    record_id: uuid.UUID, ctx: Ctx = Depends(require("attendance.read.all"))
) -> dict:
    await service.get_record_by_id(ctx.session, record_id)
    rows = await service.list_verifications(ctx.session, record_id)
    return {"items": [service.serialize_verification(row) for row in rows]}


@router.post("/attendance/{record_id}/recompute")
async def recompute(
    record_id: uuid.UUID, payload: RecomputeRequest, ctx: Ctx = Depends(require("attendance.manage"))
) -> dict:
    record = await service.get_record_by_id(ctx.session, record_id)
    if await service.period_locked_for(ctx.session, record.business_date):
        from app.core.errors import PeriodLocked

        raise PeriodLocked("This date belongs to a locked payroll period.")
    result = await service.recompute_record(ctx.session, record, ctx.settings, reason=payload.reason)
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.recomputed",
        entity_type="attendance_record",
        entity_id=record.id,
        before=result["before"],
        after=result["after"],
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.record_recalculated.v1",
        aggregate_type="attendance_record",
        aggregate_id=record.id,
        actor_user_id=ctx.actor_user_id,
        payload={"reason": payload.reason},
    )
    return service.serialize_record(record)


@router.get("/break-types")
async def get_break_types(
    include_inactive: bool = Query(False),
    ctx: Ctx = Depends(require("attendance.read.self")),
) -> dict:
    include = include_inactive and ctx.actor.has("attendance.config.manage")
    rows = await service.list_break_types(ctx.session, include_inactive=include)
    return {"items": [service.serialize_break_type(row) for row in rows]}


@router.post("/break-types", status_code=201)
async def create_break_type(
    payload: BreakTypeCreate, ctx: Ctx = Depends(require("attendance.config.manage"))
) -> dict:
    from sqlalchemy import select as _select

    existing = (
        await ctx.session.execute(_select(BreakType).where(BreakType.code == payload.code.upper()))
    ).scalar_one_or_none()
    if existing is not None:
        from app.core.errors import DuplicateConflict

        raise DuplicateConflict(f"Break type code {payload.code} already exists.")
    row = BreakType(
        code=payload.code.upper(),
        name=payload.name,
        is_paid=payload.is_paid,
        max_minutes=payload.max_minutes,
        requires_approval=payload.requires_approval,
        counts_toward_max_per_day=payload.counts_toward_max_per_day,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.break_type.created",
        entity_type="break_type",
        entity_id=row.id,
        after={"code": row.code, "name": row.name},
    )
    return service.serialize_break_type(row)


@router.patch("/break-types/{break_type_id}")
async def update_break_type(
    break_type_id: uuid.UUID, payload: BreakTypeUpdate, ctx: Ctx = Depends(require("attendance.config.manage"))
) -> dict:
    row = await ctx.session.get(BreakType, break_type_id)
    if row is None:
        raise NotFound("Break type not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await ctx.session.flush()
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.break_type.updated",
        entity_type="break_type",
        entity_id=row.id,
        after=payload.model_dump(exclude_unset=True),
    )
    return service.serialize_break_type(row)


@router.get("/holidays")
async def get_holidays(
    year: int | None = Query(None, ge=2000, le=2100),
    ctx: Ctx = Depends(require("attendance.read.self")),
) -> dict:
    target = year or business_date_of(utcnow(), ctx.settings.timezone()).year
    rows = await service.list_holidays(ctx.session, target)
    return {"items": [service.serialize_holiday(row) for row in rows]}


@router.post("/holidays", status_code=201)
async def create_holiday(
    payload: HolidayCreate, ctx: Ctx = Depends(require("attendance.config.manage"))
) -> dict:
    from sqlalchemy import select as _select

    existing = (
        await ctx.session.execute(
            _select(BusinessHoliday).where(BusinessHoliday.holiday_date == payload.holiday_date)
        )
    ).scalar_one_or_none()
    if existing is not None:
        from app.core.errors import DuplicateConflict

        raise DuplicateConflict("A holiday already exists for this date.")
    row = BusinessHoliday(
        holiday_date=payload.holiday_date,
        name=payload.name,
        is_paid=payload.is_paid,
        is_working_day=payload.is_working_day,
        notes=payload.notes,
        created_by=ctx.actor_user_id,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.holiday.created",
        entity_type="business_holiday",
        entity_id=row.id,
        after={"holiday_date": str(row.holiday_date), "name": row.name},
    )
    return service.serialize_holiday(row)


@router.delete("/holidays/{holiday_id}", status_code=204)
async def delete_holiday(
    holiday_id: uuid.UUID, ctx: Ctx = Depends(require("attendance.config.manage"))
) -> Response:
    row = await ctx.session.get(BusinessHoliday, holiday_id)
    if row is None:
        raise NotFound("Holiday not found.")
    await ctx.session.delete(row)
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.holiday.deleted",
        entity_type="business_holiday",
        entity_id=holiday_id,
        before={"holiday_date": str(row.holiday_date), "name": row.name},
    )
    return Response(status_code=204)


@router.post("/attendance/qr-tokens", status_code=201)
async def issue_qr_token(
    payload: QrIssueRequest, ctx: Ctx = Depends(require("attendance.qr.generate"))
) -> dict:
    purpose = payload.purpose if payload.purpose in {"SHOP_CHECKIN", "SHOP_CHECKOUT"} else "SHOP_CHECKIN"
    row = await service.issue_qr_token(
        ctx.session, ctx.settings, purpose=purpose, issued_by=ctx.actor_user_id
    )
    return {
        "id": row.id,
        "qr_payload": getattr(row, "qr_payload", None),
        "nonce": row.nonce,
        "expires_at": row.expires_at,
        "rotation_seconds": ctx.settings.int_("attendance.qr_rotation_seconds"),
    }


@router.get("/attendance/qr-tokens/current")
async def current_qr_token(
    purpose: str = Query("SHOP_CHECKIN"), ctx: Ctx = Depends(require("attendance.qr.generate"))
) -> dict:
    row = await service.current_qr_token(ctx.session, purpose=purpose)
    if row is None:
        raise NotFound("No QR token is currently valid; issue a new one.")
    return {
        "id": row.id,
        "nonce": row.nonce,
        "purpose": row.purpose,
        "issued_at": row.issued_at,
        "expires_at": row.expires_at,
        "rotation_seconds": ctx.settings.int_("attendance.qr_rotation_seconds"),
    }

@router.post("/attendance/corrections", status_code=201)
async def request_correction(
    payload: CorrectionCreate, ctx: Ctx = Depends(require("attendance.correct.request.self"))
) -> dict:
    employee = await _employee(ctx)
    row = await service.request_correction(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        attendance_record_id=payload.attendance_record_id,
        correction_type=payload.correction_type,
        reason=payload.reason,
        requested_check_in_at=payload.requested_check_in_at,
        requested_check_out_at=payload.requested_check_out_at,
        requested_break_start_at=payload.requested_break_start_at,
        requested_break_end_at=payload.requested_break_end_at,
        requested_notes=payload.requested_notes,
        attachment_file_id=payload.attachment_file_id,
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.correction.requested",
        entity_type="attendance_correction",
        entity_id=row.id,
        after={"correction_type": row.correction_type, "status": row.status},
        reason=payload.reason,
    )
    return service.serialize_correction(row)


@router.get("/attendance/corrections/mine")
async def my_corrections(
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("attendance.correct.request.self")),
) -> dict:
    rows, total = await service.query_corrections(
        ctx.session,
        employee_id=ctx.employee_id,
        status=status,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_correction(row) for row in rows], total, params)


@router.get("/attendance/corrections")
async def list_corrections(
    employee_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("attendance.correct.approve")),
) -> dict:
    rows, total = await service.query_corrections(
        ctx.session,
        employee_id=employee_id,
        status=status,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_correction(row) for row in rows], total, params)


@router.post("/attendance/corrections/{correction_id}/approve")
async def approve_correction(
    correction_id: uuid.UUID, payload: CorrectionDecision, ctx: Ctx = Depends(require("attendance.correct.approve"))
) -> dict:
    row = await service.get_correction(ctx.session, correction_id)
    if row.status != "PENDING":
        raise Conflict("This correction has already been decided.")
    if row.requested_by == ctx.actor_user_id:
        raise RuleViolation(
            "You cannot approve your own correction request.",
            rule_code="SELF_APPROVAL_FORBIDDEN",
        )
    if await service.period_locked_for(ctx.session, (await service.get_record_by_id(ctx.session, row.attendance_record_id)).business_date):
        from app.core.errors import PeriodLocked

        raise PeriodLocked("This date belongs to a locked payroll period.")
    changes = payload.adjust_to or {}
    if changes:
        for key in (
            "requested_check_in_at",
            "requested_check_out_at",
            "requested_break_start_at",
            "requested_break_end_at",
        ):
            if key in changes and changes[key]:
                parsed = parse_datetime(changes[key], key)
                setattr(row, key, parsed)
    row.decision_notes = payload.decision_notes
    record = await service.apply_correction(
        ctx.session, row, ctx.settings, actor_user_id=ctx.actor_user_id
    )
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.correction.approved",
        entity_type="attendance_correction",
        entity_id=row.id,
        before=row.previous_computation,
        after={"status": "APPROVED", "worked_seconds": record.worked_seconds},
        reason=payload.decision_notes,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "attendance.corrected.v1",
        aggregate_type="attendance_record",
        aggregate_id=record.id,
        actor_user_id=ctx.actor_user_id,
        payload={"correction_id": str(row.id)},
    )
    return {"correction": service.serialize_correction(row), "attendance_record": service.serialize_record(record)}


@router.post("/attendance/corrections/{correction_id}/reject")
async def reject_correction(
    correction_id: uuid.UUID, payload: CorrectionReject, ctx: Ctx = Depends(require("attendance.correct.approve"))
) -> dict:
    row = await service.get_correction(ctx.session, correction_id)
    if row.status != "PENDING":
        raise Conflict("This correction has already been decided.")
    row.status = "REJECTED"
    row.decided_by = ctx.actor_user_id
    row.decided_at = utcnow()
    row.decision_notes = payload.decision_notes
    await ctx.session.flush()
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.correction.rejected",
        entity_type="attendance_correction",
        entity_id=row.id,
        after={"status": "REJECTED"},
        reason=payload.decision_notes,
    )
    return service.serialize_correction(row)


@router.post("/attendance/corrections/{correction_id}/cancel")
async def cancel_correction(
    correction_id: uuid.UUID, payload: CorrectionCancel, ctx: Ctx = Depends(require("attendance.correct.request.self"))
) -> dict:
    row = await service.get_correction(ctx.session, correction_id)
    if row.employee_id != ctx.employee_id and not ctx.actor.has("attendance.correct.approve"):
        raise NotFound("Correction not found.")
    if row.status != "PENDING":
        raise Conflict("Only a pending correction can be cancelled.")
    row.status = "CANCELLED"
    row.decided_by = ctx.actor_user_id
    row.decided_at = utcnow()
    row.decision_notes = payload.reason
    await ctx.session.flush()
    await ctx.audit(
        category="ATTENDANCE",
        action="attendance.correction.cancelled",
        entity_type="attendance_correction",
        entity_id=row.id,
        after={"status": "CANCELLED"},
        reason=payload.reason,
    )
    return service.serialize_correction(row)