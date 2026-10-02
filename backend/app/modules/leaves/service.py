"""Leaves service: leave types, requests, balances and the balance ledger."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, DuplicateConflict, NotFound, RuleViolation, ValidationError
from app.core.money import ZERO
from app.core.timeutil import utcnow
from app.modules.directory.models import Employee
from app.modules.leaves.models import Leave, LeaveBalance, LeaveBalanceLedger, LeaveType
from app.modules.settings.service import SettingsView

REVIEW_PERMISSION = "leave.approve"


def serialize_leave_type(row: LeaveType) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "is_paid": row.is_paid,
        "requires_approval": row.requires_approval,
        "requires_attachment_after_days": row.requires_attachment_after_days,
        "max_consecutive_days": row.max_consecutive_days,
        "allow_half_day": row.allow_half_day,
        "annual_entitlement_days": f"{Decimal(row.annual_entitlement_days):.2f}",
        "accrual_mode": row.accrual_mode,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


def serialize_leave(row: Leave, leave_type: LeaveType | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "employee_id": row.employee_id,
        "leave_type_id": row.leave_type_id,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "total_days": f"{Decimal(row.total_days):.2f}",
        "is_half_day": row.is_half_day,
        "half_day_period": row.half_day_period,
        "reason": row.reason,
        "attachment_file_id": row.attachment_file_id,
        "status": row.status,
        "applied_at": row.applied_at,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_notes": row.decision_notes,
        "cancelled_at": row.cancelled_at,
        "cancel_reason": row.cancel_reason,
        "version": row.version,
    }
    if leave_type is not None:
        payload["leave_type"] = serialize_leave_type(leave_type)
    return payload


def serialize_balance(row: LeaveBalance) -> dict[str, Any]:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "leave_type_id": row.leave_type_id,
        "period_year": row.period_year,
        "entitled_days": f"{Decimal(row.entitled_days):.2f}",
        "accrued_days": f"{Decimal(row.accrued_days):.2f}",
        "carried_forward_days": f"{Decimal(row.carried_forward_days):.2f}",
        "adjustment_days": f"{Decimal(row.adjustment_days):.2f}",
        "used_days": f"{Decimal(row.used_days):.2f}",
        "pending_days": f"{Decimal(row.pending_days):.2f}",
        "available_days": f"{Decimal(row.available_days):.2f}",
        "version": row.version,
    }


def serialize_movement(row: LeaveBalanceLedger) -> dict[str, Any]:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "leave_type_id": row.leave_type_id,
        "period_year": row.period_year,
        "movement_type": row.movement_type,
        "days": f"{Decimal(row.days):.2f}",
        "leave_id": row.leave_id,
        "reference_type": row.reference_type,
        "reference_id": row.reference_id,
        "reason": row.reason,
        "created_at": row.created_at,
    }


async def get_leave_type(session: AsyncSession, leave_type_id: uuid.UUID) -> LeaveType:
    row = await session.get(LeaveType, leave_type_id)
    if row is None:
        raise NotFound("Leave type not found.")
    return row


async def list_leave_types(session: AsyncSession, *, include_inactive: bool = False) -> list[LeaveType]:
    stmt = select(LeaveType).order_by(LeaveType.sort_order, LeaveType.code)
    if not include_inactive:
        stmt = stmt.where(LeaveType.is_active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


async def get_leave(session: AsyncSession, leave_id: uuid.UUID) -> Leave:
    row = await session.get(Leave, leave_id)
    if row is None:
        raise NotFound("Leave request not found.")
    return row


async def has_approved_leave(
    session: AsyncSession, employee_id: uuid.UUID, business_date: date
) -> bool:
    row = (
        await session.execute(
            select(Leave.id).where(
                Leave.employee_id == employee_id,
                Leave.status == "APPROVED",
                Leave.start_date <= business_date,
                Leave.end_date >= business_date,
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def overlap_exists(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    start_date: date,
    end_date: date,
    exclude_leave_id: uuid.UUID | None = None,
) -> bool:
    stmt = select(Leave.id).where(
        Leave.employee_id == employee_id,
        Leave.status.in_(["PENDING", "APPROVED"]),
        Leave.start_date <= end_date,
        Leave.end_date >= start_date,
    )
    if exclude_leave_id is not None:
        stmt = stmt.where(Leave.id != exclude_leave_id)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def count_leave_days(
    settings: SettingsView, start_date: date, end_date: date, *, is_half_day: bool
) -> Decimal:
    if is_half_day:
        return Decimal("0.5")
    days = 0
    weekly_off = {int(day) for day in settings.json_("payroll.weekly_off_days") or []}
    if settings.bool_("leaves.weekend_counts_as_leave"):
        return Decimal((end_date - start_date).days + 1)
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() not in weekly_off:
            days += 1
        cursor += timedelta(days=1)
    return Decimal(days)


async def get_or_create_balance(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    leave_type: LeaveType,
    period_year: int,
) -> LeaveBalance:
    row = (
        await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == employee_id,
                LeaveBalance.leave_type_id == leave_type.id,
                LeaveBalance.period_year == period_year,
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = LeaveBalance(
        employee_id=employee_id,
        leave_type_id=leave_type.id,
        period_year=period_year,
        entitled_days=leave_type.annual_entitlement_days or ZERO,
    )
    session.add(row)
    await session.flush()
    return row

async def _movement(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    period_year: int,
    movement_type: str,
    days: Decimal,
    leave_id: uuid.UUID | None = None,
    reason: str | None = None,
    created_by: uuid.UUID | None = None,
) -> LeaveBalanceLedger:
    row = LeaveBalanceLedger(
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        period_year=period_year,
        movement_type=movement_type,
        days=days,
        leave_id=leave_id,
        reason=reason,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row


async def apply_leave(
    session: AsyncSession,
    *,
    employee: Employee,
    settings: SettingsView,
    leave_type_id: uuid.UUID,
    start_date: date,
    end_date: date,
    is_half_day: bool,
    half_day_period: str | None,
    reason: str,
    attachment_file_id: uuid.UUID | None,
    actor_user_id: uuid.UUID,
) -> Leave:
    if not settings.bool_("leaves.enabled"):
        raise RuleViolation("Leave management is disabled.", rule_code="LEAVES_DISABLED")
    leave_type = await get_leave_type(session, leave_type_id)
    if not leave_type.is_active:
        raise RuleViolation("This leave type is not available.", rule_code="LEAVE_TYPE_INACTIVE")
    if end_date < start_date:
        raise ValidationError("end_date must not precede start_date.")
    today = utcnow().date()
    if (start_date - today).days > settings.int_("leaves.max_advance_days"):
        raise RuleViolation(
            "This leave is requested too far in advance.", rule_code="LEAVE_TOO_FAR_AHEAD"
        )
    if (today - start_date).days > settings.int_("leaves.max_backdate_days"):
        raise RuleViolation("Backdated leave is not allowed.", rule_code="LEAVE_BACKDATED")
    if not settings.bool_("leaves.allow_half_day") and is_half_day:
        raise RuleViolation("Half-day leave is not enabled.", rule_code="HALF_DAY_DISABLED")
    if is_half_day and not leave_type.allow_half_day:
        raise RuleViolation(
            "This leave type does not allow half days.", rule_code="HALF_DAY_NOT_ALLOWED"
        )
    if is_half_day and start_date != end_date:
        raise ValidationError("A half-day leave must cover a single date.")
    consecutive = (end_date - start_date).days + 1
    if leave_type.max_consecutive_days and consecutive > leave_type.max_consecutive_days:
        raise RuleViolation(
            f"At most {leave_type.max_consecutive_days} consecutive days are allowed for this type.",
            rule_code="MAX_CONSECUTIVE_DAYS",
        )
    if settings.bool_("leaves.enforce_overlap") and await overlap_exists(
        session, employee_id=employee.id, start_date=start_date, end_date=end_date
    ):
        raise DuplicateConflict("This leave overlaps an existing request or approved leave.")
    threshold = settings.int_("leaves.requires_attachment_after_days")
    if (
        leave_type.requires_attachment_after_days is not None
        and consecutive > leave_type.requires_attachment_after_days
        and not attachment_file_id
    ):
        raise RuleViolation("An attachment is required for this leave.", rule_code="ATTACHMENT_REQUIRED")

    total_days = count_leave_days(settings, start_date, end_date, is_half_day=is_half_day)
    balance = await get_or_create_balance(
        session, employee_id=employee.id, leave_type=leave_type, period_year=start_date.year
    )
    if (
        leave_type.is_paid
        and not settings.bool_("leaves.allow_negative_balance")
        and balance.available_days < total_days
    ):
        raise RuleViolation(
            "Insufficient leave balance.", rule_code="INSUFFICIENT_LEAVE_BALANCE"
        )
    needs_approval = leave_type.requires_approval
    leave = Leave(
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        start_date=start_date,
        end_date=end_date,
        total_days=total_days,
        is_half_day=is_half_day,
        half_day_period=half_day_period,
        reason=reason,
        attachment_file_id=attachment_file_id,
        status="PENDING" if needs_approval else "APPROVED",
        balance_pending_hold_applied=False,
        balance_usage_applied=False,
    )
    session.add(leave)
    await session.flush()
    if needs_approval:
        balance.pending_days = Decimal(balance.pending_days) + total_days
        balance.version = int(balance.version or 1) + 1
        leave.balance_pending_hold_applied = True
        await _movement(
            session,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            period_year=start_date.year,
            movement_type="PENDING_HOLD",
            days=total_days,
            leave_id=leave.id,
            reason="Leave requested",
            created_by=actor_user_id,
        )
    else:
        balance.used_days = Decimal(balance.used_days) + total_days
        balance.version = int(balance.version or 1) + 1
        leave.balance_usage_applied = True
        await _movement(
            session,
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            period_year=start_date.year,
            movement_type="USAGE",
            days=total_days,
            leave_id=leave.id,
            reason="Auto-approved leave",
            created_by=actor_user_id,
        )
    await session.flush()
    return leave


async def decide_leave(
    session: AsyncSession,
    *,
    leave: Leave,
    settings: SettingsView,
    decision: str,
    actor_user_id: uuid.UUID,
    notes: str | None,
) -> Leave:
    if leave.status != "PENDING":
        raise Conflict(f"This leave request is already {leave.status}.")
    actor_employee = (
        await session.execute(select(Employee).where(Employee.user_id == actor_user_id))
    ).scalar_one_or_none()
    if (
        actor_employee is not None
        and actor_employee.id == leave.employee_id
        and not settings.bool_("leaves.allow_admin_self_approval")
    ):
        raise RuleViolation(
            "You cannot decide your own leave request.", rule_code="SELF_APPROVAL_FORBIDDEN"
        )
    leave_type = await get_leave_type(session, leave.leave_type_id)
    balance = (
        await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == leave.employee_id,
                LeaveBalance.leave_type_id == leave.leave_type_id,
                LeaveBalance.period_year == leave.start_date.year,
            )
        )
    ).scalar_one_or_none()
    days = Decimal(leave.total_days)
    now = utcnow()
    leave.decided_by = actor_user_id
    leave.decided_at = now
    leave.decision_notes = notes
    if decision == "APPROVED":
        if balance is not None:
            if leave.balance_pending_hold_applied:
                balance.pending_days = Decimal(balance.pending_days) - days
            balance.used_days = Decimal(balance.used_days) + days
            balance.version = int(balance.version or 1) + 1
        leave.status = "APPROVED"
        leave.balance_usage_applied = True
        await _movement(
            session,
            employee_id=leave.employee_id,
            leave_type_id=leave.leave_type_id,
            period_year=leave.start_date.year,
            movement_type="USAGE",
            days=days,
            leave_id=leave.id,
            reason="Leave approved",
            created_by=actor_user_id,
        )
        if leave.balance_pending_hold_applied:
            await _movement(
                session,
                employee_id=leave.employee_id,
                leave_type_id=leave.leave_type_id,
                period_year=leave.start_date.year,
                movement_type="PENDING_RELEASE",
                days=-days,
                leave_id=leave.id,
                reason="Pending hold released",
                created_by=actor_user_id,
            )
        leave.balance_pending_hold_applied = False
    elif decision == "REJECTED":
        if balance is not None and leave.balance_pending_hold_applied:
            balance.pending_days = Decimal(balance.pending_days) - days
            balance.version = int(balance.version or 1) + 1
            await _movement(
                session,
                employee_id=leave.employee_id,
                leave_type_id=leave.leave_type_id,
                period_year=leave.start_date.year,
                movement_type="PENDING_RELEASE",
                days=-days,
                leave_id=leave.id,
                reason="Leave rejected",
                created_by=actor_user_id,
            )
        leave.status = "REJECTED"
        leave.balance_pending_hold_applied = False
    else:
        leave.status = "PENDING"
    leave.version = int(leave.version or 1) + 1
    await session.flush()
    return leave


async def cancel_leave(
    session: AsyncSession, *, leave: Leave, actor_user_id: uuid.UUID, reason: str
) -> Leave:
    if leave.status in {"CANCELLED", "REJECTED"}:
        raise Conflict(f"This leave request is already {leave.status}.")
    days = Decimal(leave.total_days)
    balance = (
        await session.execute(
            select(LeaveBalance).where(
                LeaveBalance.employee_id == leave.employee_id,
                LeaveBalance.leave_type_id == leave.leave_type_id,
                LeaveBalance.period_year == leave.start_date.year,
            )
        )
    ).scalar_one_or_none()
    if balance is not None:
        if leave.status == "PENDING" and leave.balance_pending_hold_applied:
            balance.pending_days = Decimal(balance.pending_days) - days
            movement = "PENDING_RELEASE"
        elif leave.status == "APPROVED" and leave.balance_usage_applied:
            balance.used_days = Decimal(balance.used_days) - days
            movement = "REVERSAL"
        else:
            movement = None
        if movement:
            balance.version = int(balance.version or 1) + 1
            await _movement(
                session,
                employee_id=leave.employee_id,
                leave_type_id=leave.leave_type_id,
                period_year=leave.start_date.year,
                movement_type=movement,
                days=-days,
                leave_id=leave.id,
                reason=f"Leave cancelled: {reason}",
                created_by=actor_user_id,
            )
    leave.status = "CANCELLED"
    leave.cancelled_at = utcnow()
    leave.cancel_reason = reason
    leave.version = int(leave.version or 1) + 1
    await session.flush()
    return leave


async def list_leaves(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    status: str | None = None,
    leave_type_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Leave], int]:
    conditions = []
    if employee_id is not None:
        conditions.append(Leave.employee_id == employee_id)
    if status:
        conditions.append(Leave.status == status)
    if leave_type_id:
        conditions.append(Leave.leave_type_id == leave_type_id)
    if from_date:
        conditions.append(Leave.end_date >= from_date)
    if to_date:
        conditions.append(Leave.start_date <= to_date)
    stmt = select(Leave).order_by(Leave.applied_at.desc())
    count_stmt = select(func.count()).select_from(Leave)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def list_balances(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    period_year: int | None = None,
) -> list[LeaveBalance]:
    conditions = []
    if employee_id is not None:
        conditions.append(LeaveBalance.employee_id == employee_id)
    if period_year:
        conditions.append(LeaveBalance.period_year == period_year)
    stmt = select(LeaveBalance).order_by(LeaveBalance.period_year.desc(), LeaveBalance.leave_type_id)
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return list((await session.execute(stmt)).scalars().all())


async def list_movements(
    session: AsyncSession, balance_id: uuid.UUID
) -> list[LeaveBalanceLedger]:
    balance = await session.get(LeaveBalance, balance_id)
    if balance is None:
        raise NotFound("Leave balance not found.")
    return list(
        (
            await session.execute(
                select(LeaveBalanceLedger)
                .where(
                    LeaveBalanceLedger.employee_id == balance.employee_id,
                    LeaveBalanceLedger.leave_type_id == balance.leave_type_id,
                    LeaveBalanceLedger.period_year == balance.period_year,
                )
                .order_by(LeaveBalanceLedger.created_at)
            )
        ).scalars().all()
    )


async def adjust_balance(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    period_year: int,
    days: Decimal,
    reason: str,
    actor_user_id: uuid.UUID,
) -> LeaveBalance:
    leave_type = await get_leave_type(session, leave_type_id)
    balance = await get_or_create_balance(
        session, employee_id=employee_id, leave_type=leave_type, period_year=period_year
    )
    balance.adjustment_days = Decimal(balance.adjustment_days) + days
    balance.version = int(balance.version or 1) + 1
    await _movement(
        session,
        employee_id=employee_id,
        leave_type_id=leave_type_id,
        period_year=period_year,
        movement_type="ADJUSTMENT",
        days=days,
        reason=reason,
        created_by=actor_user_id,
    )
    await session.flush()
    return balance