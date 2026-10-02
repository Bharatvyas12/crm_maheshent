"""Leaves endpoints (docs/03_API_CONTRACT.md section 10)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.context import Ctx, parse_date, require
from app.api.idempotency import begin_idempotency, finish_idempotency, replay_response
from app.core.errors import NotFound, PermissionDenied, RuleViolation, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.modules.directory import service as directory_service
from app.modules.leaves import service

router = APIRouter(tags=["leaves"])


class LeaveTypeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    is_paid: bool = True
    requires_approval: bool = True
    requires_attachment_after_days: int | None = Field(default=None, ge=0)
    max_consecutive_days: int | None = Field(default=None, ge=1)
    allow_half_day: bool = False
    annual_entitlement_days: Decimal = Decimal("0")
    accrual_mode: str = "MANUAL"
    sort_order: int = 0


class LeaveTypeUpdate(BaseModel):
    name: str | None = None
    is_paid: bool | None = None
    requires_approval: bool | None = None
    requires_attachment_after_days: int | None = None
    max_consecutive_days: int | None = None
    allow_half_day: bool | None = None
    annual_entitlement_days: Decimal | None = None
    accrual_mode: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class LeaveApplyRequest(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    is_half_day: bool = False
    half_day_period: str | None = None
    reason: str = Field(min_length=1, max_length=1000)
    attachment_file_id: uuid.UUID | None = None


class LeaveDecisionRequest(BaseModel):
    decision_notes: str | None = Field(default=None, max_length=1000)


class LeaveCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class BalanceAdjustmentRequest(BaseModel):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    period_year: int = Field(ge=2000, le=2100)
    days: Decimal
    reason: str = Field(min_length=1, max_length=500)


@router.get("/leaves/types")
@router.get("/leave-types")
async def list_leave_types(
    include_inactive: bool = Query(False), ctx: Ctx = Depends(require("leave.read.self"))
) -> dict:
    include = include_inactive and ctx.actor.has("leave.type.manage")
    rows = await service.list_leave_types(ctx.session, include_inactive=include)
    return {"items": [service.serialize_leave_type(row) for row in rows]}


@router.post("/leave-types", status_code=201)
async def create_leave_type(
    payload: LeaveTypeCreate, ctx: Ctx = Depends(require("leave.type.manage"))
) -> dict:
    from sqlalchemy import select as _select

    from app.modules.leaves.models import LeaveType

    existing = (
        await ctx.session.execute(_select(LeaveType).where(LeaveType.code == payload.code.upper()))
    ).scalar_one_or_none()
    if existing is not None:
        from app.core.errors import DuplicateConflict

        raise DuplicateConflict(f"Leave type {payload.code} already exists.")
    row = LeaveType(**{**payload.model_dump(), "code": payload.code.upper()})
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.audit(
        category="LEAVE",
        action="leave.type.created",
        entity_type="leave_type",
        entity_id=row.id,
        after={"code": row.code, "name": row.name},
    )
    return service.serialize_leave_type(row)


@router.patch("/leave-types/{leave_type_id}")
async def update_leave_type(
    leave_type_id: uuid.UUID, payload: LeaveTypeUpdate, ctx: Ctx = Depends(require("leave.type.manage"))
) -> dict:
    row = await service.get_leave_type(ctx.session, leave_type_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await ctx.session.flush()
    await ctx.audit(
        category="LEAVE",
        action="leave.type.updated",
        entity_type="leave_type",
        entity_id=row.id,
        after=payload.model_dump(exclude_unset=True, mode="json"),
    )
    return service.serialize_leave_type(row)


@router.post("/leaves", status_code=201)
async def apply_leave(
    payload: LeaveApplyRequest, request: Request, ctx: Ctx = Depends(require("leave.apply.self"))
) -> dict:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="leaves.apply", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    employee = await directory_service.get_employee(ctx.session, ctx.employee_id)
    leave = await service.apply_leave(
        ctx.session,
        employee=employee,
        settings=ctx.settings,
        leave_type_id=payload.leave_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_half_day=payload.is_half_day,
        half_day_period=payload.half_day_period,
        reason=payload.reason,
        attachment_file_id=payload.attachment_file_id,
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="LEAVE",
        action="leave.requested",
        entity_type="leave",
        entity_id=leave.id,
        after={"status": leave.status, "days": str(leave.total_days)},
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "leave.requested.v1",
        aggregate_type="leave",
        aggregate_id=leave.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = service.serialize_leave(leave)
    await finish_idempotency(guard, 201, body)
    return body


@router.get("/leaves/mine")
async def my_leaves(
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("leave.read.self")),
) -> dict:
    rows, total = await service.list_leaves(
        ctx.session, employee_id=ctx.employee_id, status=status, offset=params.offset, limit=params.page_size
    )
    return paginated([service.serialize_leave(row) for row in rows], total, params)


@router.get("/leaves")
async def list_leaves(
    employee_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    leave_type_id: uuid.UUID | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("leave.read.all")),
) -> dict:
    rows, total = await service.list_leaves(
        ctx.session,
        employee_id=employee_id,
        status=status,
        leave_type_id=leave_type_id,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_leave(row) for row in rows], total, params)


@router.get("/leaves/{leave_id}")
async def get_leave(leave_id: uuid.UUID, ctx: Ctx = Depends(require("leave.read.self"))) -> dict:
    leave = await service.get_leave(ctx.session, leave_id)
    if leave.employee_id != ctx.actor.employee_id and not ctx.actor.has("leave.read.all"):
        raise NotFound("Leave request not found.")
    return service.serialize_leave(leave, await service.get_leave_type(ctx.session, leave.leave_type_id))


@router.post("/leaves/{leave_id}/approve")
async def approve_leave(
    leave_id: uuid.UUID, payload: LeaveDecisionRequest, ctx: Ctx = Depends(require("leave.approve"))
) -> dict:
    leave = await service.get_leave(ctx.session, leave_id)
    await service.decide_leave(
        ctx.session,
        leave=leave,
        settings=ctx.settings,
        decision="APPROVED",
        actor_user_id=ctx.actor_user_id,
        notes=payload.decision_notes,
    )
    await ctx.audit(
        category="LEAVE", action="leave.approved", entity_type="leave", entity_id=leave.id, reason=payload.decision_notes
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session, "leave.approved.v1", aggregate_type="leave", aggregate_id=leave.id, actor_user_id=ctx.actor_user_id
    )
    return service.serialize_leave(leave)


@router.post("/leaves/{leave_id}/reject")
async def reject_leave(
    leave_id: uuid.UUID, payload: LeaveDecisionRequest, ctx: Ctx = Depends(require("leave.approve"))
) -> dict:
    leave = await service.get_leave(ctx.session, leave_id)
    await service.decide_leave(
        ctx.session,
        leave=leave,
        settings=ctx.settings,
        decision="REJECTED",
        actor_user_id=ctx.actor_user_id,
        notes=payload.decision_notes,
    )
    await ctx.audit(
        category="LEAVE", action="leave.rejected", entity_type="leave", entity_id=leave.id, reason=payload.decision_notes
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session, "leave.rejected.v1", aggregate_type="leave", aggregate_id=leave.id, actor_user_id=ctx.actor_user_id
    )
    return service.serialize_leave(leave)


@router.post("/leaves/{leave_id}/request-modification")
async def request_modification(
    leave_id: uuid.UUID, payload: LeaveDecisionRequest, ctx: Ctx = Depends(require("leave.approve"))
) -> dict:
    leave = await service.get_leave(ctx.session, leave_id)
    if leave.status != "PENDING":
        from app.core.errors import Conflict

        raise Conflict("Only a pending leave can be sent back for modification.")
    leave.decision_notes = payload.decision_notes
    await ctx.session.flush()
    await ctx.audit(
        category="LEAVE", action="leave.modification_requested", entity_type="leave", entity_id=leave.id, reason=payload.decision_notes
    )
    return service.serialize_leave(leave)


@router.post("/leaves/{leave_id}/cancel")
async def cancel_leave(
    leave_id: uuid.UUID, payload: LeaveCancelRequest, ctx: Ctx = Depends(require("leave.cancel.self"))
) -> dict:
    leave = await service.get_leave(ctx.session, leave_id)
    if leave.employee_id != ctx.actor.employee_id and not ctx.actor.has("leave.cancel.any"):
        raise NotFound("Leave request not found.")
    if leave.employee_id == ctx.actor.employee_id and leave.status == "APPROVED" and not ctx.actor.has("leave.cancel.any"):
        raise RuleViolation("An approved leave can only be cancelled by an administrator.")
    await service.cancel_leave(
        ctx.session, leave=leave, actor_user_id=ctx.actor_user_id, reason=payload.reason
    )
    await ctx.audit(
        category="LEAVE", action="leave.cancelled", entity_type="leave", entity_id=leave.id, reason=payload.reason
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session, "leave.cancelled.v1", aggregate_type="leave", aggregate_id=leave.id, actor_user_id=ctx.actor_user_id
    )
    return service.serialize_leave(leave)


@router.get("/leave-balances/mine")
async def my_balances(
    period_year: int | None = Query(None), ctx: Ctx = Depends(require("leave.read.self"))
) -> dict:
    rows = await service.list_balances(
        ctx.session, employee_id=ctx.employee_id, period_year=period_year
    )
    return {"items": [service.serialize_balance(row) for row in rows]}


@router.get("/leave-balances")
async def list_balances(
    employee_id: uuid.UUID | None = Query(None),
    period_year: int | None = Query(None),
    ctx: Ctx = Depends(require("leave.read.all")),
) -> dict:
    rows = await service.list_balances(
        ctx.session, employee_id=employee_id, period_year=period_year
    )
    return {"items": [service.serialize_balance(row) for row in rows]}


@router.get("/leave-balances/{balance_id}/movements")
async def balance_movements(
    balance_id: uuid.UUID, ctx: Ctx = Depends(require("leave.read.all"))
) -> dict:
    rows = await service.list_movements(ctx.session, balance_id)
    return {"items": [service.serialize_movement(row) for row in rows]}


@router.post("/leave-balances/adjustments", status_code=201)
async def adjust_balance(
    payload: BalanceAdjustmentRequest, ctx: Ctx = Depends(require("leave.balance.manage"))
) -> dict:
    balance = await service.adjust_balance(
        ctx.session,
        employee_id=payload.employee_id,
        leave_type_id=payload.leave_type_id,
        period_year=payload.period_year,
        days=payload.days,
        reason=payload.reason,
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="LEAVE",
        action="leave.balance.adjusted",
        entity_type="leave_balance",
        entity_id=balance.id,
        after={"days": str(payload.days)},
        reason=payload.reason,
    )
    return service.serialize_balance(balance)