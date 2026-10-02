"""Ledger, advances and payroll endpoints (docs/03_API_CONTRACT.md section 11)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.context import Ctx, parse_date, require, require_any
from app.api.idempotency import begin_idempotency, finish_idempotency, replay_response
from app.core.errors import NotFound, PermissionDenied, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.modules.directory import service as directory_service
from app.modules.payroll import service

router = APIRouter(tags=["payroll"])

LEDGER_TYPES = (
    "SALARY_PAYABLE",
    "OVERTIME_PAY",
    "BONUS",
    "ADJUSTMENT",
    "OTHER_DEDUCTION",
    "ADVANCE_REPAYMENT",
)


class LedgerEntryCreate(BaseModel):
    employee_id: uuid.UUID
    entry_type: str
    amount: Decimal = Field(gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    business_date: date | None = None
    period_year: int | None = Field(default=None, ge=2000, le=2100)
    period_month: int | None = Field(default=None, ge=1, le=12)
    reason: str | None = Field(default=None, max_length=500)
    direction: str | None = None


class LedgerReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AdvanceCreateRequest(BaseModel):
    employee_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    issued_on: date
    reason: str = Field(min_length=1, max_length=500)
    installment_count: int = Field(default=1, ge=1, le=60)


class AdvanceDecisionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RepaymentRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class WriteOffRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RunCreateRequest(BaseModel):
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    notes: str | None = Field(default=None, max_length=1000)


class UnlockRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@router.get("/ledger/me")
async def my_ledger(
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("ledger.read.self")),
) -> dict:
    rows, total = await service.list_ledger_entries(
        ctx.session,
        employee_id=ctx.employee_id,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_ledger_entry(row) for row in rows], total, params)


@router.get("/ledger")
async def list_ledger(
    employee_id: uuid.UUID | None = Query(None),
    entry_type: str | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    period_year: int | None = Query(None),
    period_month: int | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("ledger.read.all")),
) -> dict:
    rows, total = await service.list_ledger_entries(
        ctx.session,
        employee_id=employee_id,
        entry_type=entry_type,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        period_year=period_year,
        period_month=period_month,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_ledger_entry(row) for row in rows], total, params)


@router.post("/ledger/entries", status_code=201)
async def create_ledger_entry(
    payload: LedgerEntryCreate, ctx: Ctx = Depends(require("ledger.entry.create"))
) -> dict:
    if payload.entry_type not in LEDGER_TYPES:
        raise ValidationError(f"Unsupported ledger entry type: {payload.entry_type}")
    await directory_service.get_employee(ctx.session, payload.employee_id)
    row = await service.post_ledger_entry(
        ctx.session,
        employee_id=payload.employee_id,
        entry_type=payload.entry_type,
        amount=payload.amount,
        actor_user_id=ctx.actor_user_id,
        reason=payload.reason,
        currency=(payload.currency or ctx.settings.currency()).upper(),
        business_date=payload.business_date,
        period_year=payload.period_year,
        period_month=payload.period_month,
        direction=payload.direction,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="FINANCIAL",
        action="ledger.entry_created",
        entity_type="employee_ledger_entry",
        entity_id=row.id,
        after={
            "employee_id": str(payload.employee_id),
            "entry_type": row.entry_type,
            "amount": str(row.amount),
        },
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "payroll.ledger_entry_created.v1",
        aggregate_type="employee_ledger_entry",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"entry_type": row.entry_type},
    )
    return service.serialize_ledger_entry(row)


@router.post("/ledger/entries/{entry_id}/reverse", status_code=201)
async def reverse_entry(
    entry_id: uuid.UUID, payload: LedgerReverseRequest, ctx: Ctx = Depends(require("ledger.entry.adjust"))
) -> dict:
    entry = await service.get_ledger_entry(ctx.session, entry_id)
    await service.assert_period_not_locked(ctx.session, entry.business_date)
    reversal = await service.reverse_ledger_entry(
        ctx.session, entry=entry, actor_user_id=ctx.actor_user_id, reason=payload.reason
    )
    await ctx.audit(
        category="FINANCIAL",
        action="ledger.entry_reversed",
        entity_type="employee_ledger_entry",
        entity_id=reversal.id,
        before={"reversed_entry_id": str(entry.id), "amount": str(entry.amount)},
        reason=payload.reason,
    )
    return service.serialize_ledger_entry(reversal)


@router.get("/ledger/{entry_id}")
async def get_ledger_entry(entry_id: uuid.UUID, ctx: Ctx = Depends(require("ledger.read.self"))) -> dict:
    entry = await service.get_ledger_entry(ctx.session, entry_id)
    if entry.employee_id != ctx.actor.employee_id and not ctx.actor.has("ledger.read.all"):
        raise NotFound("Ledger entry not found.")
    return service.serialize_ledger_entry(entry)


@router.get("/ledger/balance/{employee_id}")
async def ledger_balance(
    employee_id: uuid.UUID, currency: str | None = Query(None), ctx: Ctx = Depends(require("ledger.read.self"))
) -> dict:
    if employee_id != ctx.actor.employee_id and not ctx.actor.has("ledger.read.all"):
        raise PermissionDenied("You may only read your own ledger balance.")
    return await service.ledger_balance(ctx.session, employee_id, currency)


@router.get("/advances/mine")
async def my_advances(
    params: PageParams = Depends(page_params), ctx: Ctx = Depends(require("advance.read.self"))
) -> dict:
    from sqlalchemy import func, select

    from app.modules.payroll.models import Advance

    count_stmt = select(func.count()).select_from(Advance).where(Advance.employee_id == ctx.employee_id)
    total = int((await ctx.session.execute(count_stmt)).scalar_one())
    stmt = (
        select(Advance)
        .where(Advance.employee_id == ctx.employee_id)
        .order_by(Advance.issued_on.desc())
        .offset(params.offset)
        .limit(params.page_size)
    )
    rows = list((await ctx.session.execute(stmt)).scalars().all())
    return paginated([service.serialize_advance(row) for row in rows], total, params)


@router.get("/advances")
async def list_advances(
    employee_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("advance.read.all")),
) -> dict:
    from sqlalchemy import func, select

    from app.modules.payroll.models import Advance

    conditions = []
    if employee_id:
        conditions.append(Advance.employee_id == employee_id)
    if status:
        conditions.append(Advance.status == status)
    stmt = select(Advance).order_by(Advance.issued_on.desc())
    count_stmt = select(func.count()).select_from(Advance)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = int((await ctx.session.execute(count_stmt)).scalar_one())
    rows = list((await ctx.session.execute(stmt.offset(params.offset).limit(params.page_size))).scalars().all())
    return paginated([service.serialize_advance(row) for row in rows], total, params)


@router.get("/advances/{advance_id}")
async def get_advance(advance_id: uuid.UUID, ctx: Ctx = Depends(require("advance.read.self"))) -> dict:
    advance = await service.get_advance(ctx.session, advance_id)
    if advance.employee_id != ctx.actor.employee_id and not ctx.actor.has("advance.read.all"):
        raise NotFound("Advance not found.")
    return service.serialize_advance(advance, await service.list_installments(ctx.session, advance.id))


@router.post("/advances", status_code=201)
async def create_advance(
    payload: AdvanceCreateRequest, request: Request, ctx: Ctx = Depends(require("advance.create"))
) -> dict:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="advances.create", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    employee = await directory_service.get_employee(ctx.session, payload.employee_id)
    advance = await service.create_advance(
        ctx.session,
        employee=employee,
        amount=payload.amount,
        currency=(payload.currency or ctx.settings.currency()).upper(),
        issued_on=payload.issued_on,
        reason=payload.reason,
        installment_count=payload.installment_count,
        actor_user_id=ctx.actor_user_id,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="FINANCIAL",
        action="advance.created",
        entity_type="advance",
        entity_id=advance.id,
        after={"employee_id": str(employee.id), "amount": str(advance.amount), "status": advance.status},
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "payroll.advance_issued.v1",
        aggregate_type="advance",
        aggregate_id=advance.id,
        actor_user_id=ctx.actor_user_id,
        payload={"amount": str(advance.amount)},
    )
    body = service.serialize_advance(advance, await service.list_installments(ctx.session, advance.id))
    await finish_idempotency(guard, 201, body)
    return body


@router.post("/advances/{advance_id}/approve")
async def approve_advance(
    advance_id: uuid.UUID, payload: AdvanceDecisionRequest, ctx: Ctx = Depends(require("advance.approve"))
) -> dict:
    advance = await service.get_advance(ctx.session, advance_id)
    await service.approve_advance(
        ctx.session, advance=advance, actor_user_id=ctx.actor_user_id, settings=ctx.settings
    )
    await ctx.audit(
        category="FINANCIAL", action="advance.approved", entity_type="advance", entity_id=advance.id, reason=payload.reason
    )
    return service.serialize_advance(advance, await service.list_installments(ctx.session, advance.id))


@router.post("/advances/{advance_id}/reject")
async def reject_advance(
    advance_id: uuid.UUID, payload: AdvanceDecisionRequest, ctx: Ctx = Depends(require("advance.approve"))
) -> dict:
    advance = await service.get_advance(ctx.session, advance_id)
    await service.reject_advance(
        ctx.session, advance=advance, actor_user_id=ctx.actor_user_id, reason=payload.reason or "Rejected"
    )
    await ctx.audit(
        category="FINANCIAL", action="advance.rejected", entity_type="advance", entity_id=advance.id, reason=payload.reason
    )
    return service.serialize_advance(advance)


@router.post("/advances/{advance_id}/repayments", status_code=201)
async def advance_repayment(
    advance_id: uuid.UUID, payload: RepaymentRequest, ctx: Ctx = Depends(require("ledger.entry.create"))
) -> dict:
    advance = await service.get_advance(ctx.session, advance_id)
    await service.cash_repayment(
        ctx.session,
        advance=advance,
        amount=payload.amount,
        actor_user_id=ctx.actor_user_id,
        reason=payload.reason,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="FINANCIAL",
        action="advance.repayment",
        entity_type="advance",
        entity_id=advance.id,
        after={"amount": str(payload.amount), "outstanding": str(advance.outstanding_amount)},
        reason=payload.reason,
    )
    return service.serialize_advance(advance, await service.list_installments(ctx.session, advance.id))


@router.post("/advances/{advance_id}/write-off")
async def write_off_advance(
    advance_id: uuid.UUID, payload: WriteOffRequest, ctx: Ctx = Depends(require_any("advance.approve"))
) -> dict:
    if not ctx.actor.has("ledger.entry.adjust"):
        raise PermissionDenied("Writing off an advance requires ledger adjustment permission.")
    advance = await service.get_advance(ctx.session, advance_id)
    await service.write_off_advance(
        ctx.session, advance=advance, actor_user_id=ctx.actor_user_id, reason=payload.reason
    )
    await ctx.audit(
        category="FINANCIAL", action="advance.written_off", entity_type="advance", entity_id=advance.id, reason=payload.reason
    )
    return service.serialize_advance(advance)

@router.get("/payroll/runs")
async def list_runs(
    status: str | None = Query(None),
    period_year: int | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("salary.read.all")),
) -> dict:
    rows, total = await service.list_runs(
        ctx.session, status=status, period_year=period_year, offset=params.offset, limit=params.page_size
    )
    return paginated([service.serialize_payroll_run(row) for row in rows], total, params)


@router.post("/payroll/runs", status_code=201)
async def create_run(payload: RunCreateRequest, ctx: Ctx = Depends(require("salary.compute"))) -> dict:
    run = await service.create_run(
        ctx.session,
        period_year=payload.period_year,
        period_month=payload.period_month,
        actor_user_id=ctx.actor_user_id,
        notes=payload.notes,
    )
    await ctx.audit(
        category="FINANCIAL",
        action="payroll.run_created",
        entity_type="payroll_run",
        entity_id=run.id,
        after={"period": f"{run.period_year}-{run.period_month:02d}"},
    )
    return service.serialize_payroll_run(run)


@router.get("/payroll/runs/{run_id}")
async def get_run(run_id: uuid.UUID, ctx: Ctx = Depends(require("salary.read.all"))) -> dict:
    run = await service.get_run(ctx.session, run_id)
    records, total = await service.list_salary_records(
        ctx.session, run_id=run.id, limit=200
    )
    return {
        **service.serialize_payroll_run(run),
        "salary_records": [service.serialize_salary_record(row) for row in records],
        "record_count": total,
    }


@router.post("/payroll/runs/{run_id}/compute")
async def compute_run(run_id: uuid.UUID, ctx: Ctx = Depends(require("salary.compute"))) -> dict:
    run = await service.get_run(ctx.session, run_id)
    run, records = await service.compute_run(
        ctx.session, run=run, settings=ctx.settings, actor_user_id=ctx.actor_user_id
    )
    await ctx.audit(
        category="FINANCIAL",
        action="payroll.computed",
        entity_type="payroll_run",
        entity_id=run.id,
        after={"records": len(records)},
    )
    return {
        **service.serialize_payroll_run(run),
        "salary_records": [service.serialize_salary_record(row) for row in records],
    }


@router.post("/payroll/runs/{run_id}/finalize")
async def finalize_run(
    run_id: uuid.UUID, request: Request, ctx: Ctx = Depends(require("salary.finalize"))
) -> dict:
    guard, replay = await begin_idempotency(ctx, request, endpoint="payroll.finalize", payload={"run_id": str(run_id)})
    if replay is not None:
        return replay_response(replay)
    run = await service.get_run(ctx.session, run_id)
    await service.finalize_run(
        ctx.session, run=run, actor_user_id=ctx.actor_user_id, settings=ctx.settings
    )
    await ctx.audit(
        category="FINANCIAL",
        action="payroll.finalized",
        entity_type="payroll_run",
        entity_id=run.id,
        after={"period": f"{run.period_year}-{run.period_month:02d}"},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "payroll.salary_finalized.v1",
        aggregate_type="payroll_run",
        aggregate_id=run.id,
        actor_user_id=ctx.actor_user_id,
        payload={"period": f"{run.period_year}-{run.period_month:02d}"},
    )
    body = service.serialize_payroll_run(run)
    await finish_idempotency(guard, 200, body)
    return body


@router.post("/payroll/runs/{run_id}/lock")
async def lock_run(run_id: uuid.UUID, ctx: Ctx = Depends(require("payroll.lock"))) -> dict:
    run = await service.get_run(ctx.session, run_id)
    await service.lock_run(ctx.session, run=run, actor_user_id=ctx.actor_user_id)
    await ctx.audit(
        category="FINANCIAL", action="payroll.locked", entity_type="payroll_run", entity_id=run.id
    )
    return service.serialize_payroll_run(run)


@router.post("/payroll/runs/{run_id}/unlock")
async def unlock_run(
    run_id: uuid.UUID, payload: UnlockRequest, ctx: Ctx = Depends(require("payroll.unlock"))
) -> dict:
    run = await service.get_run(ctx.session, run_id)
    await service.unlock_run(
        ctx.session, run=run, actor_user_id=ctx.actor_user_id, reason=payload.reason
    )
    await ctx.audit(
        category="FINANCIAL",
        action="payroll.unlocked",
        entity_type="payroll_run",
        entity_id=run.id,
        reason=payload.reason,
    )
    return service.serialize_payroll_run(run)


@router.post("/payroll/runs/{run_id}/mark-paid")
async def mark_paid(run_id: uuid.UUID, ctx: Ctx = Depends(require("payroll.pay"))) -> dict:
    run = await service.get_run(ctx.session, run_id)
    await service.mark_paid(
        ctx.session, run=run, actor_user_id=ctx.actor_user_id, settings=ctx.settings
    )
    await ctx.audit(
        category="FINANCIAL", action="payroll.marked_paid", entity_type="payroll_run", entity_id=run.id
    )
    return service.serialize_payroll_run(run)


@router.get("/salary-records/me")
async def my_salary_records(
    period_year: int | None = Query(None),
    period_month: int | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("salary.read.self")),
) -> dict:
    rows, total = await service.list_salary_records(
        ctx.session,
        employee_id=ctx.employee_id,
        period_year=period_year,
        period_month=period_month,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_salary_record(row) for row in rows], total, params)


@router.get("/salary-records")
async def list_salary_records(
    employee_id: uuid.UUID | None = Query(None),
    period_year: int | None = Query(None),
    period_month: int | None = Query(None),
    run_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("salary.read.all")),
) -> dict:
    rows, total = await service.list_salary_records(
        ctx.session,
        employee_id=employee_id,
        period_year=period_year,
        period_month=period_month,
        run_id=run_id,
        status=status,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_salary_record(row) for row in rows], total, params)


@router.get("/salary-records/{record_id}")
async def get_salary_record(
    record_id: uuid.UUID, ctx: Ctx = Depends(require("salary.read.self"))
) -> dict:
    record = await service.get_salary_record(ctx.session, record_id)
    if record.employee_id != ctx.actor.employee_id and not ctx.actor.has("salary.read.all"):
        raise NotFound("Salary record not found.")
    return service.serialize_salary_record(record, include_breakdown=True)


@router.get("/salary-records/{record_id}/payslip")
async def get_payslip(
    record_id: uuid.UUID, ctx: Ctx = Depends(require("salary.read.self"))
) -> dict:
    record = await service.get_salary_record(ctx.session, record_id)
    if record.employee_id != ctx.actor.employee_id and not ctx.actor.has("salary.read.all"):
        raise NotFound("Salary record not found.")
    return await service.build_payslip(ctx.session, record)