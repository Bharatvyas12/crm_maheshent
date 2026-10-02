"""Payroll service: employee ledger, advances, payroll runs and salary computation.

Money is Decimal end to end. Every salary record stores the rule snapshot, the
inputs used and the calculation breakdown so historical payroll is explainable
without re-deriving it from today's settings (docs/04_BUSINESS_RULES.md BR-4.9).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, DuplicateConflict, NotFound, PeriodLocked, RuleViolation, ValidationError
from app.core.money import ZERO, money_str, quantize_money, quantize_rate, to_decimal
from app.core.timeutil import business_month_bounds, utcnow
from app.modules.directory import service as directory_service
from app.modules.directory.models import Employee, EmployeeCompensation
from app.modules.payroll.models import (
    Advance,
    AdvanceInstallment,
    EmployeeLedgerEntry,
    PayrollRun,
    PayrollRuleSnapshot,
    SalaryRecord,
)
from app.modules.settings.service import SettingsView, json_safe
from app.modules.settings.registry import SETTINGS_BY_KEY

CREDIT_TYPES = {"SALARY_PAYABLE", "OVERTIME_PAY", "BONUS", "ADJUSTMENT"}
DEBIT_TYPES = {
    "ADVANCE_ISSUED",
    "ADVANCE_REPAYMENT",
    "LEAVE_DEDUCTION",
    "LATE_DEDUCTION",
    "OTHER_DEDUCTION",
    "PAYMENT_MADE",
}
LEDGER_ENTRY_TYPES = CREDIT_TYPES | DEBIT_TYPES | {"REVERSAL"}

RULESETTING_KEYS = tuple(
    key
    for key in SETTINGS_BY_KEY
    if key.startswith(("payroll.", "advance.", "ledger."))
) + (
    "attendance.required_daily_hours",
    "attendance.full_day_min_hours",
    "attendance.half_day_min_hours",
    "attendance.partial_day_min_hours",
    "org.currency",
)


def _money(value: Any, mode: str) -> Decimal:
    return quantize_money(value, mode)


def serialize_ledger_entry(row: EmployeeLedgerEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "entry_type": row.entry_type,
        "direction": row.direction,
        "amount": money_str(row.amount),
        "currency": row.currency,
        "business_date": row.business_date,
        "period_year": row.period_year,
        "period_month": row.period_month,
        "salary_record_id": row.salary_record_id,
        "advance_id": row.advance_id,
        "payroll_run_id": row.payroll_run_id,
        "reference_type": row.reference_type,
        "reference_id": row.reference_id,
        "reason": row.reason,
        "created_by": row.created_by,
        "reverses_entry_id": row.reverses_entry_id,
        "created_at": row.created_at,
    }


def serialize_advance(row: Advance, installments: list[AdvanceInstallment] | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "employee_id": row.employee_id,
        "amount": money_str(row.amount),
        "currency": row.currency,
        "issued_on": row.issued_on,
        "issued_by": row.issued_by,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at,
        "reason": row.reason,
        "repayment_mode": row.repayment_mode,
        "installment_count": row.installment_count,
        "installment_amount": money_str(row.installment_amount) if row.installment_amount is not None else None,
        "outstanding_amount": money_str(row.outstanding_amount),
        "status": row.status,
        "closed_at": row.closed_at,
        "version": row.version,
    }
    if installments is not None:
        payload["installments"] = [
            {
                "id": item.id,
                "installment_no": item.installment_no,
                "due_period_year": item.due_period_year,
                "due_period_month": item.due_period_month,
                "amount": money_str(item.amount),
                "recovered_amount": money_str(item.recovered_amount),
                "status": item.status,
            }
            for item in installments
        ]
    return payload


def serialize_salary_record(row: SalaryRecord, *, include_breakdown: bool = False) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "employee_id": row.employee_id,
        "payroll_run_id": row.payroll_run_id,
        "period_year": row.period_year,
        "period_month": row.period_month,
        "currency": row.currency,
        "compensation_type": row.compensation_type,
        "base_rate": f"{Decimal(row.base_rate):.4f}",
        "present_days": f"{Decimal(row.present_days):.2f}",
        "leave_days": f"{Decimal(row.leave_days):.2f}",
        "absent_days": f"{Decimal(row.absent_days):.2f}",
        "half_days": f"{Decimal(row.half_days):.2f}",
        "weekly_off_days": f"{Decimal(row.weekly_off_days):.2f}",
        "holiday_days": f"{Decimal(row.holiday_days):.2f}",
        "payable_days": f"{Decimal(row.payable_days):.2f}",
        "worked_seconds": row.worked_seconds,
        "overtime_seconds": row.overtime_seconds,
        "gross_amount": money_str(row.gross_amount),
        "overtime_amount": money_str(row.overtime_amount),
        "bonus_amount": money_str(row.bonus_amount),
        "leave_deduction": money_str(row.leave_deduction),
        "late_deduction": money_str(row.late_deduction),
        "advance_deduction": money_str(row.advance_deduction),
        "other_deduction": money_str(row.other_deduction),
        "total_deductions": money_str(row.total_deductions),
        "net_amount": money_str(row.net_amount),
        "status": row.status,
        "rule_snapshot_id": row.rule_snapshot_id,
        "computed_at": row.computed_at,
        "finalized_at": row.finalized_at,
        "paid_at": row.paid_at,
        "version": row.version,
    }
    if include_breakdown:
        payload["calculation_breakdown"] = row.calculation_breakdown
        payload["inputs_snapshot"] = row.inputs_snapshot
    return payload


def serialize_payroll_run(row: PayrollRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "period_year": row.period_year,
        "period_month": row.period_month,
        "status": row.status,
        "created_by": row.created_by,
        "started_at": row.started_at,
        "computed_at": row.computed_at,
        "finalized_by": row.finalized_by,
        "finalized_at": row.finalized_at,
        "locked_at": row.locked_at,
        "paid_at": row.paid_at,
        "notes": row.notes,
        "version": row.version,
    }


# ---------------------------------------------------------------------------
# Period locks
# ---------------------------------------------------------------------------


async def is_period_locked(session: AsyncSession, business_date: date) -> bool:
    row = (
        await session.execute(
            select(PayrollRun.status).where(
                PayrollRun.period_year == business_date.year,
                PayrollRun.period_month == business_date.month,
                PayrollRun.status == "LOCKED",
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def assert_period_not_locked(session: AsyncSession, business_date: date) -> None:
    if await is_period_locked(session, business_date):
        raise PeriodLocked("This date belongs to a locked payroll period.")

# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def _direction_for(entry_type: str) -> str:
    return "CREDIT" if entry_type in CREDIT_TYPES else "DEBIT"


async def post_ledger_entry(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    entry_type: str,
    amount: Decimal | str,
    actor_user_id: uuid.UUID | None,
    reason: str | None,
    currency: str,
    business_date: date | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    salary_record_id: uuid.UUID | None = None,
    advance_id: uuid.UUID | None = None,
    payroll_run_id: uuid.UUID | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
    reverses_entry_id: uuid.UUID | None = None,
    direction: str | None = None,
    settings: SettingsView | None = None,
) -> EmployeeLedgerEntry:
    if entry_type not in LEDGER_ENTRY_TYPES:
        raise ValidationError(f"Unsupported ledger entry type: {entry_type}")
    value = _money(amount, "HALF_UP")
    if value < 0:
        raise ValidationError("Ledger amounts must not be negative; use the entry type to set direction.")
    if settings is not None and settings.bool_("ledger.require_reason") and not reason:
        raise RuleViolation("A reason is required for a ledger entry.", rule_code="REASON_REQUIRED")
    row = EmployeeLedgerEntry(
        employee_id=employee_id,
        entry_type=entry_type,
        direction=direction or _direction_for(entry_type),
        amount=value,
        currency=currency,
        business_date=business_date or utcnow().date(),
        period_year=period_year,
        period_month=period_month,
        salary_record_id=salary_record_id,
        advance_id=advance_id,
        payroll_run_id=payroll_run_id,
        reference_type=reference_type,
        reference_id=reference_id,
        reason=reason,
        created_by=actor_user_id,
        reverses_entry_id=reverses_entry_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get_ledger_entry(session: AsyncSession, entry_id: uuid.UUID) -> EmployeeLedgerEntry:
    row = await session.get(EmployeeLedgerEntry, entry_id)
    if row is None:
        raise NotFound("Ledger entry not found.")
    return row


async def reverse_ledger_entry(
    session: AsyncSession,
    *,
    entry: EmployeeLedgerEntry,
    actor_user_id: uuid.UUID,
    reason: str,
) -> EmployeeLedgerEntry:
    already = (
        await session.execute(
            select(EmployeeLedgerEntry.id).where(
                EmployeeLedgerEntry.reverses_entry_id == entry.id
            )
        )
    ).scalar_one_or_none()
    if already:
        raise Conflict("This entry has already been reversed.")
    reversal = EmployeeLedgerEntry(
        employee_id=entry.employee_id,
        entry_type="REVERSAL",
        direction="DEBIT" if entry.direction == "CREDIT" else "CREDIT",
        amount=entry.amount,
        currency=entry.currency,
        business_date=utcnow().date(),
        period_year=entry.period_year,
        period_month=entry.period_month,
        advance_id=entry.advance_id,
        payroll_run_id=entry.payroll_run_id,
        reference_type="ledger_entry",
        reference_id=entry.id,
        reason=reason,
        created_by=actor_user_id,
        reverses_entry_id=entry.id,
    )
    session.add(reversal)
    await session.flush()
    return reversal


async def ledger_balance(session: AsyncSession, employee_id: uuid.UUID, currency: str | None = None) -> dict[str, Any]:
    stmt = select(
        EmployeeLedgerEntry.direction, func.coalesce(func.sum(EmployeeLedgerEntry.amount), 0)
    ).where(EmployeeLedgerEntry.employee_id == employee_id)
    if currency:
        stmt = stmt.where(EmployeeLedgerEntry.currency == currency)
    rows = (await session.execute(stmt.group_by(EmployeeLedgerEntry.direction))).all()
    credit = ZERO
    debit = ZERO
    for direction, total in rows:
        if direction == "CREDIT":
            credit = _money(total, "HALF_UP")
        else:
            debit = _money(total, "HALF_UP")
    return {
        "employee_id": employee_id,
        "currency": currency,
        "total_credits": money_str(credit),
        "total_debits": money_str(debit),
        "net_balance": money_str(credit - debit),
    }


async def list_ledger_entries(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    entry_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[EmployeeLedgerEntry], int]:
    conditions = []
    if employee_id:
        conditions.append(EmployeeLedgerEntry.employee_id == employee_id)
    if entry_type:
        conditions.append(EmployeeLedgerEntry.entry_type == entry_type)
    if from_date:
        conditions.append(EmployeeLedgerEntry.business_date >= from_date)
    if to_date:
        conditions.append(EmployeeLedgerEntry.business_date <= to_date)
    if period_year:
        conditions.append(EmployeeLedgerEntry.period_year == period_year)
    if period_month:
        conditions.append(EmployeeLedgerEntry.period_month == period_month)
    stmt = select(EmployeeLedgerEntry).order_by(
        EmployeeLedgerEntry.business_date.desc(), EmployeeLedgerEntry.created_at.desc()
    )
    count_stmt = select(func.count()).select_from(EmployeeLedgerEntry)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


# ---------------------------------------------------------------------------
# Advances
# ---------------------------------------------------------------------------


async def get_advance(session: AsyncSession, advance_id: uuid.UUID) -> Advance:
    row = await session.get(Advance, advance_id)
    if row is None:
        raise NotFound("Advance not found.")
    return row


async def list_installments(
    session: AsyncSession, advance_id: uuid.UUID
) -> list[AdvanceInstallment]:
    return list(
        (
            await session.execute(
                select(AdvanceInstallment)
                .where(AdvanceInstallment.advance_id == advance_id)
                .order_by(AdvanceInstallment.installment_no)
            )
        ).scalars().all()
    )


async def outstanding_total(session: AsyncSession, employee_id: uuid.UUID) -> Decimal:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Advance.outstanding_amount), 0)).where(
                Advance.employee_id == employee_id,
                Advance.status.in_(["APPROVED", "ACTIVE", "PARTIALLY_RECOVERED"]),
            )
        )
    ).scalar_one()
    return _money(total, "HALF_UP")


async def create_advance(
    session: AsyncSession,
    *,
    employee: Employee,
    amount: Decimal,
    currency: str,
    issued_on: date,
    reason: str,
    installment_count: int,
    actor_user_id: uuid.UUID,
    settings: SettingsView,
) -> Advance:
    if not settings.bool_("advance.enabled"):
        raise RuleViolation("Advances are disabled.", rule_code="ADVANCES_DISABLED")
    value = _money(amount, "HALF_UP")
    if value <= 0:
        raise ValidationError("The advance amount must be greater than zero.")
    max_count = settings.int_("advance.max_installment_count")
    if installment_count < 1 or installment_count > max_count:
        raise ValidationError(f"installment_count must be between 1 and {max_count}.")
    min_installment = settings.decimal_("advance.min_installment_amount")
    if value / installment_count < min_installment:
        raise RuleViolation(
            f"Each installment must be at least {money_str(min_installment)}.",
            rule_code="INSTALLMENT_TOO_SMALL",
        )
    outstanding = await outstanding_total(session, employee.id)
    compensation = await directory_service.current_compensation(session, employee.id, issued_on)
    if compensation is not None:
        max_percent = settings.decimal_("advance.max_outstanding_percent_of_salary")
        if compensation.compensation_type == "FIXED_MONTHLY":
            monthly = Decimal(compensation.rate)
        elif compensation.compensation_type == "DAILY_WAGE":
            monthly = Decimal(compensation.rate) * Decimal(30)
        else:
            monthly = Decimal(compensation.rate) * Decimal(settings.get("attendance.required_daily_hours")) * Decimal(30)
        limit = _money(monthly * max_percent / Decimal(100), "HALF_UP")
        if outstanding + value > limit:
            raise RuleViolation(
                "The total outstanding advance would exceed the configured limit.",
                rule_code="ADVANCE_LIMIT_EXCEEDED",
            )
    installment_amount = _money(value / installment_count, "HALF_UP")
    advance = Advance(
        employee_id=employee.id,
        amount=value,
        currency=currency,
        issued_on=issued_on,
        issued_by=actor_user_id,
        reason=reason,
        installment_count=installment_count,
        installment_amount=installment_amount,
        outstanding_amount=value,
        status="PENDING_APPROVAL" if settings.bool_("advance.requires_approval") else "APPROVED",
    )
    session.add(advance)
    await session.flush()
    if not settings.bool_("advance.requires_approval"):
        await _activate_advance(session, advance, actor_user_id=actor_user_id, actor=None)
    return advance


async def _activate_advance(
    session: AsyncSession,
    advance: Advance,
    *,
    actor_user_id: uuid.UUID,
    actor: Employee | None,
) -> None:
    await session.flush()
    now = utcnow()
    count = int(advance.installment_count or 1)
    total = Decimal(advance.amount)
    base = _money(total / count, "HALF_UP")
    allocated = ZERO
    start = advance.issued_on
    for index in range(1, count + 1):
        if index == count:
            amount = _money(total - allocated, "HALF_UP")
        else:
            amount = base
            allocated += amount
        month_offset = index - 1
        year = start.year + (start.month - 1 + month_offset) // 12
        month = (start.month - 1 + month_offset) % 12 + 1
        session.add(
            AdvanceInstallment(
                advance_id=advance.id,
                installment_no=index,
                due_period_year=year,
                due_period_month=month,
                amount=amount,
                recovered_amount=ZERO,
                status="PENDING",
            )
        )
    advance.status = "ACTIVE"
    advance.approved_by = actor_user_id
    advance.approved_at = now
    await session.flush()
    await post_ledger_entry(
        session,
        employee_id=advance.employee_id,
        entry_type="ADVANCE_ISSUED",
        amount=Decimal(advance.amount),
        actor_user_id=actor_user_id,
        reason=advance.reason,
        currency=advance.currency,
        business_date=advance.issued_on,
        advance_id=advance.id,
        reference_type="advance",
        reference_id=advance.id,
    )


async def approve_advance(
    session: AsyncSession, *, advance: Advance, actor_user_id: uuid.UUID, settings: SettingsView
) -> Advance:
    if advance.status != "PENDING_APPROVAL":
        raise Conflict(f"This advance is {advance.status} and cannot be approved.")
    await _activate_advance(session, advance, actor_user_id=actor_user_id, actor=None)
    return advance


async def reject_advance(
    session: AsyncSession, *, advance: Advance, actor_user_id: uuid.UUID, reason: str
) -> Advance:
    if advance.status != "PENDING_APPROVAL":
        raise Conflict(f"This advance is {advance.status} and cannot be rejected.")
    advance.status = "REJECTED"
    advance.approved_by = actor_user_id
    advance.approved_at = utcnow()
    await session.flush()
    return advance


async def cash_repayment(
    session: AsyncSession,
    *,
    advance: Advance,
    amount: Decimal,
    actor_user_id: uuid.UUID,
    reason: str,
    settings: SettingsView,
) -> Advance:
    if not settings.bool_("advance.allow_cash_repayment"):
        raise RuleViolation("Cash repayment is not enabled.", rule_code="CASH_REPAYMENT_DISABLED")
    if advance.status not in {"ACTIVE", "PARTIALLY_RECOVERED"}:
        raise Conflict(f"This advance is {advance.status} and cannot be repaid.")
    value = _money(amount, "HALF_UP")
    if value <= 0:
        raise ValidationError("The repayment amount must be greater than zero.")
    if value > Decimal(advance.outstanding_amount):
        raise RuleViolation(
            "The repayment exceeds the outstanding amount.", rule_code="OVERPAYMENT"
        )
    advance.outstanding_amount = _money(Decimal(advance.outstanding_amount) - value, "HALF_UP")
    if Decimal(advance.outstanding_amount) <= 0:
        advance.outstanding_amount = ZERO
        advance.status = "CLOSED"
        advance.closed_at = utcnow()
    else:
        advance.status = "PARTIALLY_RECOVERED"
    advance.version = int(advance.version or 1) + 1
    await post_ledger_entry(
        session,
        employee_id=advance.employee_id,
        entry_type="ADVANCE_REPAYMENT",
        amount=value,
        actor_user_id=actor_user_id,
        reason=reason,
        currency=advance.currency,
        advance_id=advance.id,
        reference_type="advance",
        reference_id=advance.id,
    )
    await session.flush()
    return advance


async def write_off_advance(
    session: AsyncSession, *, advance: Advance, actor_user_id: uuid.UUID, reason: str
) -> Advance:
    if advance.status in {"CLOSED", "WRITTEN_OFF", "REJECTED"}:
        raise Conflict(f"This advance is {advance.status} and cannot be written off.")
    outstanding = Decimal(advance.outstanding_amount)
    advance.status = "WRITTEN_OFF"
    advance.closed_at = utcnow()
    advance.outstanding_amount = ZERO
    advance.version = int(advance.version or 1) + 1
    await post_ledger_entry(
        session,
        employee_id=advance.employee_id,
        entry_type="ADJUSTMENT",
        amount=outstanding,
        actor_user_id=actor_user_id,
        reason=f"Advance written off: {reason}",
        currency=advance.currency,
        direction="DEBIT",
        advance_id=advance.id,
        reference_type="advance",
        reference_id=advance.id,
    )
    await session.flush()
    return advance

# ---------------------------------------------------------------------------
# Payroll runs and salary computation
# ---------------------------------------------------------------------------

DAY_CALENDAR = "CALENDAR"
DAY_WEEKLY_OFF = "WEEKLY_OFF"
DAY_BUSINESS_CALENDAR = "BUSINESS_CALENDAR"


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> PayrollRun:
    row = await session.get(PayrollRun, run_id)
    if row is None:
        raise NotFound("Payroll run not found.")
    return row


async def create_run(
    session: AsyncSession,
    *,
    period_year: int,
    period_month: int,
    actor_user_id: uuid.UUID,
    notes: str | None,
) -> PayrollRun:
    if not 1 <= period_month <= 12:
        raise ValidationError("period_month must be between 1 and 12.")
    existing = (
        await session.execute(
            select(PayrollRun).where(
                PayrollRun.period_year == period_year, PayrollRun.period_month == period_month
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateConflict(
            f"A payroll run already exists for {period_year}-{period_month:02d}."
        )
    run = PayrollRun(
        period_year=period_year,
        period_month=period_month,
        status="DRAFT",
        created_by=actor_user_id,
        started_at=utcnow(),
        notes=notes,
    )
    session.add(run)
    await session.flush()
    return run


def rule_snapshot_payload(settings: SettingsView) -> dict[str, Any]:
    return {key: json_safe(settings.get(key)) for key in RULESETTING_KEYS}


def rule_snapshot_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def ensure_rule_snapshot(
    session: AsyncSession, run: PayrollRun, settings: SettingsView, actor_user_id: uuid.UUID
) -> PayrollRuleSnapshot:
    payload = rule_snapshot_payload(settings)
    digest = rule_snapshot_hash(payload)
    existing = (
        await session.execute(
            select(PayrollRuleSnapshot).where(
                PayrollRuleSnapshot.payroll_run_id == run.id,
                PayrollRuleSnapshot.scope == "GLOBAL",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    row = PayrollRuleSnapshot(
        scope="GLOBAL",
        payroll_run_id=run.id,
        settings_snapshot=payload,
        settings_hash=digest,
        created_by=actor_user_id,
        note=f"Rule snapshot for {run.period_year}-{run.period_month:02d}",
    )
    session.add(row)
    await session.flush()
    return row


async def working_days_for(
    session: AsyncSession, settings: SettingsView, year: int, month: int, tz
) -> int:
    basis = settings.str_("payroll.working_days_basis")
    first, last = business_month_bounds(year, month, tz)
    total = (last - first).days + 1
    if basis == DAY_CALENDAR:
        return total
    weekly_off = {int(day) for day in settings.json_("payroll.weekly_off_days") or []}
    days = 0
    cursor = first
    while cursor <= last:
        if cursor.weekday() not in weekly_off:
            days += 1
        cursor += timedelta(days=1)
    if basis == DAY_BUSINESS_CALENDAR:
        from app.modules.attendance.models import BusinessHoliday

        holidays = (
            await session.execute(
                select(BusinessHoliday.holiday_date, BusinessHoliday.is_working_day).where(
                    BusinessHoliday.holiday_date >= first,
                    BusinessHoliday.holiday_date <= last,
                )
            )
        ).all()
        for holiday_date, is_working in holidays:
            if not is_working and holiday_date.weekday() not in weekly_off:
                days -= 1
            elif is_working and holiday_date.weekday() in weekly_off:
                days += 1
    return days

async def _period_context(
    session: AsyncSession, settings: SettingsView, year: int, month: int
):
    from app.modules.attendance.models import AttendanceRecord, BusinessHoliday
    from app.modules.leaves.models import Leave, LeaveType

    tz = settings.timezone()
    first, last = business_month_bounds(year, month, tz)
    records = list(
        (
            await session.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.business_date >= first,
                    AttendanceRecord.business_date <= last,
                )
            )
        ).scalars().all()
    )
    holidays = dict(
        (
            await session.execute(
                select(BusinessHoliday.holiday_date, BusinessHoliday.is_paid).where(
                    BusinessHoliday.holiday_date >= first,
                    BusinessHoliday.holiday_date <= last,
                )
            )
        ).all()
    )
    paid_leave_dates: set[tuple[uuid.UUID, date]] = set()
    leave_rows = (
        await session.execute(
            select(Leave.employee_id, Leave.start_date, Leave.end_date, LeaveType.is_paid).join(
                LeaveType, LeaveType.id == Leave.leave_type_id
            ).where(
                Leave.status == "APPROVED",
                Leave.start_date <= last,
                Leave.end_date >= first,
            )
        )
    ).all()
    for employee_id, start_date, end_date, is_paid in leave_rows:
        if not is_paid:
            continue
        cursor = max(start_date, first)
        stop = min(end_date, last)
        while cursor <= stop:
            paid_leave_dates.add((employee_id, cursor))
            cursor += timedelta(days=1)
    return first, last, records, holidays, paid_leave_dates


async def compute_run(
    session: AsyncSession,
    *,
    run: PayrollRun,
    settings: SettingsView,
    actor_user_id: uuid.UUID,
) -> tuple[PayrollRun, list[SalaryRecord]]:
    if run.status in {"LOCKED", "PAID"}:
        raise Conflict(f"A payroll run in status {run.status} cannot be recomputed.")
    if run.status == "FINALIZED":
        raise Conflict("A finalized payroll run must be unlocked before recomputation.")
    if not settings.bool_("payroll.enabled"):
        raise RuleViolation("Payroll is disabled.", rule_code="PAYROLL_DISABLED")
    snapshot = await ensure_rule_snapshot(session, run, settings, actor_user_id)
    first, last, records, holidays, paid_leave_dates = await _period_context(
        session, settings, run.period_year, run.period_month
    )
    by_employee: dict[uuid.UUID, list[Any]] = {}
    for record in records:
        by_employee.setdefault(record.employee_id, []).append(record)
    employees = list(
        (
            await session.execute(
                select(Employee).where(Employee.employment_status.in_(["ACTIVE", "INACTIVE", "SUSPENDED", "EXITED"]))
            )
        ).scalars().all()
    )
    results: list[SalaryRecord] = []
    for employee in employees:
        if employee.date_of_joining > last:
            continue
        if employee.date_of_exit is not None and employee.date_of_exit < first:
            continue
        salary = await _compute_employee_salary(
            session,
            run=run,
            employee=employee,
            settings=settings,
            snapshot=snapshot,
            period=(first, last),
            attendance=by_employee.get(employee.id, []),
            holidays=holidays,
            paid_leave_dates=paid_leave_dates,
            actor_user_id=actor_user_id,
        )
        if salary is not None:
            results.append(salary)
    run.status = "COMPUTED"
    run.computed_at = utcnow()
    run.version = int(run.version or 1) + 1
    await session.flush()
    return run, results

async def _compute_employee_salary(
    session: AsyncSession,
    *,
    run: PayrollRun,
    employee: Employee,
    settings: SettingsView,
    snapshot: PayrollRuleSnapshot,
    period: tuple[date, date],
    attendance: list[Any],
    holidays: dict[date, bool],
    paid_leave_dates: set[tuple[uuid.UUID, date]],
    actor_user_id: uuid.UUID,
) -> SalaryRecord | None:
    first, last = period
    mode = settings.str_("payroll.rounding_mode")
    compensation = await directory_service.current_compensation(session, employee.id, last)
    if compensation is None:
        return None
    currency = compensation.currency or settings.currency()
    comp_type = compensation.compensation_type
    rate = Decimal(compensation.rate)
    working_days = await working_days_for(
        session, settings, run.period_year, run.period_month, settings.timezone()
    )
    denominator = working_days
    if settings.str_("payroll.payable_day_basis") == "FIXED_DAYS_IN_MONTH":
        denominator = settings.int_("payroll.fixed_days_in_month")
    if denominator <= 0:
        denominator = working_days or 1

    weekly_off = {int(day) for day in settings.json_("payroll.weekly_off_days") or []}
    required_daily_hours = settings.decimal_("attendance.required_daily_hours")
    fraction_mode = settings.str_("payroll.partial_day_pay_fraction_mode")
    fixed_fraction = settings.decimal_("payroll.partial_day_fixed_fraction")

    present_days = Decimal(0)
    half_days = Decimal(0)
    absent_days = Decimal(0)
    leave_days = Decimal(0)
    weekly_off_days = Decimal(0)
    holiday_days = Decimal(0)
    payable = Decimal(0)
    worked_seconds_total = 0
    overtime_seconds_total = 0
    late_occurrences = 0
    unpaid_leave_days = Decimal(0)
    per_day: list[dict[str, Any]] = []

    for record in attendance:
        day = record.business_date
        status = record.status
        classification = record.day_classification
        credit = Decimal(0)
        kind = classification
        worked_seconds_total += int(record.worked_seconds or 0)
        overtime_seconds_total += int(record.overtime_seconds or 0)
        if record.late_minutes and record.late_minutes > 0:
            late_occurrences += 1
        if status in {"PRESENT", "INCOMPLETE"}:
            if classification == "FULL_DAY":
                credit = Decimal("1.00")
            elif classification == "HALF_DAY":
                credit = Decimal("0.50")
            elif classification == "PARTIAL_DAY":
                if fraction_mode == "PRO_RATA_HOURS":
                    hours = Decimal(int(record.worked_seconds or 0)) / Decimal(3600)
                    credit = min(Decimal("1.00"), hours / required_daily_hours)
                elif fraction_mode == "FIXED_FRACTION":
                    credit = fixed_fraction
                else:
                    credit = Decimal(0)
            if credit == 0:
                credit = Decimal(0)
                if classification == "FULL_DAY":
                    present_days += 1
                else:
                    absent_days += 1
            else:
                if classification == "FULL_DAY":
                    present_days += 1
                elif classification == "HALF_DAY":
                    half_days += 1
        elif status == "ON_LEAVE":
            leave_days += 1
            if (employee.id, day) in paid_leave_dates and settings.bool_(
                "payroll.paid_leave_counts_as_payable"
            ):
                credit = Decimal("1.00")
            else:
                unpaid_leave_days += 1
                credit = Decimal(0)
        elif status == "HOLIDAY":
            holiday_days += 1
            if settings.bool_("payroll.holiday_pay_enabled") and holidays.get(day, False):
                credit = Decimal("1.00")
        elif status == "WEEKLY_OFF":
            weekly_off_days += 1
            if settings.bool_("payroll.weekly_off_pay_enabled"):
                credit = Decimal("1.00")
        else:
            absent_days += 1
            credit = Decimal(0)
        payable += credit
        per_day.append(
            {
                "date": day.isoformat(),
                "status": status,
                "classification": kind,
                "credit": f"{credit:.2f}",
            }
        )

    if comp_type == "FIXED_MONTHLY":
        gross = rate * (payable / Decimal(denominator))
    elif comp_type == "DAILY_WAGE":
        gross = rate * payable
    else:
        gross = rate * (Decimal(worked_seconds_total) / Decimal(3600))
    gross = _money(gross, mode)

    overtime_amount = ZERO
    if settings.bool_("payroll.overtime_enabled") and settings.bool_("attendance.overtime_enabled"):
        if comp_type == "FIXED_MONTHLY":
            hourly = rate / (Decimal(denominator) * required_daily_hours)
        elif comp_type == "DAILY_WAGE":
            hourly = rate / required_daily_hours
        else:
            hourly = rate
        overtime_amount = _money(
            (Decimal(overtime_seconds_total) / Decimal(3600))
            * hourly
            * settings.decimal_("payroll.overtime_rate_multiplier"),
            mode,
        )

    leave_deduction = ZERO
    if settings.bool_("payroll.unpaid_leave_deduction_enabled") and unpaid_leave_days > 0:
        if comp_type == "FIXED_MONTHLY":
            daily_rate = rate / Decimal(denominator)
        elif comp_type == "DAILY_WAGE":
            daily_rate = rate
        else:
            daily_rate = rate * required_daily_hours
        leave_deduction = _money(unpaid_leave_days * daily_rate, mode)

    late_deduction = ZERO
    if settings.bool_("payroll.late_deduction_enabled"):
        threshold = settings.int_("payroll.late_deduction_after_minutes")
        occurrences = 0
        for record in attendance:
            if (record.late_minutes or 0) > threshold:
                occurrences += 1
        late_deduction = _money(
            Decimal(occurrences) * settings.decimal_("payroll.late_deduction_per_occurrence"), mode
        )

    advance_deduction, advance_note = await _advance_deduction_for(
        session, employee_id=employee.id, period=(first, last), gross=gross, settings=settings, mode=mode
    )
    other_deduction = await _other_deductions_for(
        session, employee_id=employee.id, run=run, mode=mode
    )
    bonus_amount = await _bonus_for(session, employee_id=employee.id, run=run, mode=mode)

    total_deductions = _money(
        leave_deduction + late_deduction + advance_deduction + other_deduction, mode
    )
    net = _money(gross + overtime_amount + bonus_amount - total_deductions, mode)
    carry_forward = ZERO
    if net < 0:
        carry_forward = _money(-net, mode)
        net = ZERO
        total_deductions = _money(gross + overtime_amount + bonus_amount, mode)

    breakdown = {
        "steps": {
            "working_days": working_days,
            "denominator": denominator,
            "payable_days": f"{payable:.2f}",
            "gross": money_str(gross),
            "overtime_amount": money_str(overtime_amount),
            "bonus_amount": money_str(bonus_amount),
            "leave_deduction": money_str(leave_deduction),
            "late_deduction": money_str(late_deduction),
            "advance_deduction": money_str(advance_deduction),
            "other_deduction": money_str(other_deduction),
            "total_deductions": money_str(total_deductions),
            "net_amount": money_str(net),
        },
        "advance_note": advance_note,
        "carry_forward": money_str(carry_forward),
        "per_day": per_day,
        "rounding_mode": mode,
    }
    inputs = {
        "compensation_id": str(compensation.id),
        "compensation_type": comp_type,
        "rate": f"{rate:.4f}",
        "attendance_days": len(attendance),
        "worked_seconds": worked_seconds_total,
        "overtime_seconds": overtime_seconds_total,
        "late_occurrences": late_occurrences,
        "unpaid_leave_days": f"{unpaid_leave_days:.2f}",
        "rule_snapshot_hash": snapshot.settings_hash,
    }

    existing = (
        await session.execute(
            select(SalaryRecord).where(
                SalaryRecord.employee_id == employee.id,
                SalaryRecord.period_year == run.period_year,
                SalaryRecord.period_month == run.period_month,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status != "DRAFT":
            raise Conflict(
                f"The salary record for {employee.employee_code} is {existing.status} and is immutable."
            )
        record = existing
        record.version = int(record.version or 1) + 1
    else:
        record = SalaryRecord(
            employee_id=employee.id,
            payroll_run_id=run.id,
            period_year=run.period_year,
            period_month=run.period_month,
            currency=currency,
            compensation_type=comp_type,
            base_rate=rate,
        )
        session.add(record)
    record.currency = currency
    record.compensation_type = comp_type
    record.base_rate = rate
    record.present_days = present_days
    record.leave_days = leave_days
    record.absent_days = absent_days
    record.half_days = half_days
    record.weekly_off_days = weekly_off_days
    record.holiday_days = holiday_days
    record.payable_days = _money(payable, mode)
    record.worked_seconds = worked_seconds_total
    record.overtime_seconds = overtime_seconds_total
    record.gross_amount = gross
    record.overtime_amount = overtime_amount
    record.bonus_amount = bonus_amount
    record.leave_deduction = leave_deduction
    record.late_deduction = late_deduction
    record.advance_deduction = advance_deduction
    record.other_deduction = other_deduction
    record.net_amount = net
    record.status = "DRAFT"
    record.inputs_snapshot = inputs
    record.calculation_breakdown = breakdown
    record.rule_snapshot_id = snapshot.id
    record.computed_at = utcnow()
    record.computed_by = actor_user_id
    await session.flush()
    return record

async def _advance_deduction_for(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    period: tuple[date, date],
    gross: Decimal,
    settings: SettingsView,
    mode: str,
) -> tuple[Decimal, str]:
    first, last = period
    advances = list(
        (
            await session.execute(
                select(Advance)
                .where(
                    Advance.employee_id == employee_id,
                    Advance.status.in_(["ACTIVE", "PARTIALLY_RECOVERED"]),
                )
                .order_by(Advance.issued_on)
            )
        ).scalars().all()
    )
    if not advances:
        return ZERO, "no active advance"
    max_percent = settings.decimal_("advance.max_percent_recovered_per_month")
    cap = _money(gross * max_percent / Decimal(100), mode)
    remaining_cap = cap
    total = ZERO
    notes: list[str] = []
    for advance in advances:
        if remaining_cap <= 0:
            break
        outstanding = Decimal(advance.outstanding_amount)
        if outstanding <= 0:
            continue
        installment = (
            await session.execute(
                select(AdvanceInstallment)
                .where(
                    AdvanceInstallment.advance_id == advance.id,
                    AdvanceInstallment.status.in_(["PENDING", "PARTIALLY_RECOVERED"]),
                    or_(
                        AdvanceInstallment.due_period_year < last.year,
                        and_(
                            AdvanceInstallment.due_period_year == last.year,
                            AdvanceInstallment.due_period_month <= last.month,
                        ),
                    ),
                )
                .order_by(AdvanceInstallment.installment_no)
                .limit(1)
            )
        ).scalar_one_or_none()
        due = Decimal(installment.amount) - Decimal(installment.recovered_amount) if installment else outstanding
        take = min(outstanding, due, remaining_cap)
        take = _money(take, mode)
        if take <= 0:
            continue
        remaining_cap = _money(remaining_cap - take, mode)
        total = _money(total + take, mode)
        advance.outstanding_amount = _money(outstanding - take, mode)
        if Decimal(advance.outstanding_amount) <= 0:
            advance.outstanding_amount = ZERO
            advance.status = "CLOSED"
            advance.closed_at = utcnow()
        else:
            advance.status = "PARTIALLY_RECOVERED"
        advance.version = int(advance.version or 1) + 1
        if installment is not None:
            installment.recovered_amount = _money(
                Decimal(installment.recovered_amount) + take, mode
            )
            if Decimal(installment.recovered_amount) >= Decimal(installment.amount):
                installment.status = "RECOVERED"
            else:
                installment.status = "PARTIALLY_RECOVERED"
        notes.append(f"advance {advance.id}: {money_str(take)}")
    await session.flush()
    return total, "; ".join(notes) if notes else "nothing due"


async def _other_deductions_for(
    session: AsyncSession, *, employee_id: uuid.UUID, run: PayrollRun, mode: str
) -> Decimal:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(EmployeeLedgerEntry.amount), 0)).where(
                EmployeeLedgerEntry.employee_id == employee_id,
                EmployeeLedgerEntry.entry_type == "OTHER_DEDUCTION",
                EmployeeLedgerEntry.period_year == run.period_year,
                EmployeeLedgerEntry.period_month == run.period_month,
            )
        )
    ).scalar_one()
    return _money(total, mode)


async def _bonus_for(
    session: AsyncSession, *, employee_id: uuid.UUID, run: PayrollRun, mode: str
) -> Decimal:
    total = (
        await session.execute(
            select(func.coalesce(func.sum(EmployeeLedgerEntry.amount), 0)).where(
                EmployeeLedgerEntry.employee_id == employee_id,
                EmployeeLedgerEntry.entry_type == "BONUS",
                EmployeeLedgerEntry.period_year == run.period_year,
                EmployeeLedgerEntry.period_month == run.period_month,
            )
        )
    ).scalar_one()
    return _money(total, mode)


async def finalize_run(
    session: AsyncSession, *, run: PayrollRun, actor_user_id: uuid.UUID, settings: SettingsView
) -> PayrollRun:
    if run.status == "LOCKED":
        raise Conflict("A locked payroll run cannot be finalized.")
    if run.status != "COMPUTED":
        raise Conflict("Only a computed payroll run can be finalized.")
    if settings.bool_("payroll.require_attendance_corrections_resolved"):
        pending = (
            await session.execute(
                select(func.count())
                .select_from(SalaryRecord)
                .join(
                    PayrollRun, PayrollRun.id == SalaryRecord.payroll_run_id
                )
                .where(SalaryRecord.payroll_run_id == run.id)
            )
        ).scalar_one()
        del pending
    records = list(
        (
            await session.execute(
                select(SalaryRecord).where(SalaryRecord.payroll_run_id == run.id)
            )
        ).scalars().all()
    )
    now = utcnow()
    for record in records:
        if record.status != "DRAFT":
            continue
        record.status = "FINALIZED"
        record.finalized_at = now
        record.finalized_by = actor_user_id
        record.version = int(record.version or 1) + 1
        await post_ledger_entry(
            session,
            employee_id=record.employee_id,
            entry_type="SALARY_PAYABLE",
            amount=Decimal(record.net_amount),
            actor_user_id=actor_user_id,
            reason=f"Salary {record.period_year}-{record.period_month:02d}",
            currency=record.currency,
            period_year=record.period_year,
            period_month=record.period_month,
            salary_record_id=record.id,
            payroll_run_id=run.id,
            reference_type="salary_record",
            reference_id=record.id,
        )
    run.status = "FINALIZED"
    run.finalized_by = actor_user_id
    run.finalized_at = now
    run.version = int(run.version or 1) + 1
    await session.flush()
    return run


async def lock_run(
    session: AsyncSession, *, run: PayrollRun, actor_user_id: uuid.UUID
) -> PayrollRun:
    if run.status == "LOCKED":
        return run
    if run.status != "FINALIZED":
        raise Conflict("Only a finalized payroll run can be locked.")
    run.status = "LOCKED"
    run.locked_at = utcnow()
    run.version = int(run.version or 1) + 1
    await session.flush()
    return run


async def unlock_run(
    session: AsyncSession, *, run: PayrollRun, actor_user_id: uuid.UUID, reason: str
) -> PayrollRun:
    if run.status != "LOCKED":
        raise Conflict("Only a locked payroll run can be unlocked.")
    run.status = "FINALIZED"
    run.locked_at = None
    run.notes = (run.notes + "\n" if run.notes else "") + f"Unlocked: {reason}"
    run.version = int(run.version or 1) + 1
    await session.flush()
    return run


async def mark_paid(
    session: AsyncSession, *, run: PayrollRun, actor_user_id: uuid.UUID, settings: SettingsView
) -> PayrollRun:
    if run.status == "PAID":
        return run
    if settings.bool_("payroll.require_finalize_before_pay") and run.status not in {
        "FINALIZED",
        "LOCKED",
    }:
        raise Conflict("The payroll run must be finalized before it can be marked paid.")
    records = list(
        (
            await session.execute(
                select(SalaryRecord).where(SalaryRecord.payroll_run_id == run.id)
            )
        ).scalars().all()
    )
    now = utcnow()
    for record in records:
        if record.status == "PAID":
            continue
        payment = await post_ledger_entry(
            session,
            employee_id=record.employee_id,
            entry_type="PAYMENT_MADE",
            amount=Decimal(record.net_amount),
            actor_user_id=actor_user_id,
            reason=f"Salary paid {record.period_year}-{record.period_month:02d}",
            currency=record.currency,
            period_year=record.period_year,
            period_month=record.period_month,
            salary_record_id=record.id,
            payroll_run_id=run.id,
            reference_type="salary_record",
            reference_id=record.id,
        )
        record.status = "PAID"
        record.paid_at = now
        record.paid_by = actor_user_id
        record.ledger_entry_id = payment.id
        record.version = int(record.version or 1) + 1
    run.status = "PAID"
    run.paid_at = now
    run.version = int(run.version or 1) + 1
    await session.flush()
    return run


async def list_runs(
    session: AsyncSession,
    *,
    status: str | None = None,
    period_year: int | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[PayrollRun], int]:
    conditions = []
    if status:
        conditions.append(PayrollRun.status == status)
    if period_year:
        conditions.append(PayrollRun.period_year == period_year)
    stmt = select(PayrollRun).order_by(
        PayrollRun.period_year.desc(), PayrollRun.period_month.desc()
    )
    count_stmt = select(func.count()).select_from(PayrollRun)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def get_salary_record(session: AsyncSession, record_id: uuid.UUID) -> SalaryRecord:
    row = await session.get(SalaryRecord, record_id)
    if row is None:
        raise NotFound("Salary record not found.")
    return row


async def list_salary_records(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    period_year: int | None = None,
    period_month: int | None = None,
    run_id: uuid.UUID | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[SalaryRecord], int]:
    conditions = []
    if employee_id:
        conditions.append(SalaryRecord.employee_id == employee_id)
    if period_year:
        conditions.append(SalaryRecord.period_year == period_year)
    if period_month:
        conditions.append(SalaryRecord.period_month == period_month)
    if run_id:
        conditions.append(SalaryRecord.payroll_run_id == run_id)
    if status:
        conditions.append(SalaryRecord.status == status)
    stmt = select(SalaryRecord).order_by(
        SalaryRecord.period_year.desc(), SalaryRecord.period_month.desc()
    )
    count_stmt = select(func.count()).select_from(SalaryRecord)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def build_payslip(session: AsyncSession, record: SalaryRecord) -> dict[str, Any]:
    employee = await directory_service.get_employee(session, record.employee_id)
    lines: list[dict[str, Any]] = [
        {"label": "Gross", "amount": money_str(record.gross_amount), "kind": "EARNING"},
        {"label": "Overtime", "amount": money_str(record.overtime_amount), "kind": "EARNING"},
        {"label": "Bonus", "amount": money_str(record.bonus_amount), "kind": "EARNING"},
        {"label": "Leave deduction", "amount": money_str(record.leave_deduction), "kind": "DEDUCTION"},
        {"label": "Late deduction", "amount": money_str(record.late_deduction), "kind": "DEDUCTION"},
        {"label": "Advance recovery", "amount": money_str(record.advance_deduction), "kind": "DEDUCTION"},
        {"label": "Other deductions", "amount": money_str(record.other_deduction), "kind": "DEDUCTION"},
    ]
    return {
        "salary_record": serialize_salary_record(record, include_breakdown=True),
        "employee": {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "full_name": employee.full_name,
            "department": employee.department,
            "designation": employee.designation,
        },
        "lines": lines,
        "total_deductions": money_str(record.total_deductions),
        "net_amount": money_str(record.net_amount),
        "status": record.status,
    }