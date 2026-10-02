"""Reports service: a read-only facade over the domain modules (architecture 7.5)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import hours_str, money_str
from app.core.timeutil import business_date_of, utcnow
from app.modules.settings.service import SettingsView

REPORT_CATALOG: list[dict[str, Any]] = [
    {"report_type": "attendance", "title": "Attendance register", "permission": "report.attendance", "formats": ["CSV", "XLSX"]},
    {"report_type": "work-hours", "title": "Worked hours", "permission": "report.attendance", "formats": ["CSV", "XLSX"]},
    {"report_type": "breaks", "title": "Break usage", "permission": "report.attendance", "formats": ["CSV", "XLSX"]},
    {"report_type": "overtime", "title": "Overtime", "permission": "report.attendance", "formats": ["CSV", "XLSX"]},
    {"report_type": "tasks", "title": "Task completion", "permission": "report.tasks", "formats": ["CSV", "XLSX"]},
    {"report_type": "orders", "title": "Order throughput", "permission": "report.orders", "formats": ["CSV", "XLSX"]},
    {"report_type": "leaves", "title": "Leave usage", "permission": "report.leaves", "formats": ["CSV", "XLSX"]},
    {"report_type": "advances", "title": "Advances outstanding", "permission": "report.ledger", "formats": ["CSV", "XLSX"]},
    {"report_type": "ledger", "title": "Employee ledger", "permission": "report.ledger", "formats": ["CSV", "XLSX"]},
    {"report_type": "salary", "title": "Salary register", "permission": "report.salary", "formats": ["CSV", "XLSX"]},
    {"report_type": "complaints", "title": "Complaints", "permission": "report.complaints", "formats": ["CSV", "XLSX"]},
    {"report_type": "dashboard-summary", "title": "Dashboard summary", "permission": None, "formats": ["JSON"]},
]

REPORT_TYPES = {item["report_type"] for item in REPORT_CATALOG}


def validate_range(settings: SettingsView, from_date: date, to_date: date) -> None:
    from app.core.errors import ValidationError

    if from_date > to_date:
        raise ValidationError("from must not be after to.")
    max_days = settings.int_("reports.max_range_days")
    if (to_date - from_date).days > max_days:
        raise ValidationError(f"Report range must not exceed {max_days} days.")


async def attendance_report(
    session: AsyncSession,
    *,
    from_date: date,
    to_date: date,
    employee_id: uuid.UUID | None = None,
    department: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    from app.modules.attendance.models import AttendanceRecord
    from app.modules.directory.models import Employee

    stmt = (
        select(AttendanceRecord, Employee.employee_code, Employee.full_name, Employee.department)
        .join(Employee, Employee.id == AttendanceRecord.employee_id)
        .where(
            AttendanceRecord.business_date >= from_date,
            AttendanceRecord.business_date <= to_date,
        )
        .order_by(AttendanceRecord.business_date, Employee.employee_code)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if department:
        stmt = stmt.where(Employee.department == department)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "business_date": record.business_date.isoformat(),
            "employee_code": code,
            "full_name": name,
            "department": dept,
            "status": record.status,
            "day_classification": record.day_classification,
            "worked_seconds": record.worked_seconds,
            "worked_hours": hours_str(record.worked_seconds),
            "break_seconds": record.break_seconds,
            "overtime_seconds": record.overtime_seconds,
            "late_minutes": record.late_minutes,
            "early_checkout_minutes": record.early_checkout_minutes,
        }
        for record, code, name, dept in rows
    ]


async def order_report(
    session: AsyncSession, *, from_date: date, to_date: date, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.orders.models import Order

    stmt = (
        select(Order)
        .where(func.date(Order.created_at) >= from_date, func.date(Order.created_at) <= to_date)
        .order_by(Order.created_at)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(Order.current_assignee_id == employee_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "order_code": row.order_code,
            "status": row.status,
            "current_assignee_id": str(row.current_assignee_id) if row.current_assignee_id else None,
            "order_amount": money_str(row.order_amount),
            "created_at": row.created_at.isoformat(),
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "reassign_count": row.reassign_count,
        }
        for row in rows
    ]


async def task_report(
    session: AsyncSession, *, from_date: date, to_date: date, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.tasks.models import TaskAssignment

    stmt = (
        select(TaskAssignment)
        .where(
            func.date(TaskAssignment.assigned_at) >= from_date,
            func.date(TaskAssignment.assigned_at) <= to_date,
        )
        .order_by(TaskAssignment.assigned_at)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(TaskAssignment.employee_id == employee_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "assignment_id": str(row.id),
            "task_id": str(row.task_id),
            "employee_id": str(row.employee_id),
            "status": row.status,
            "attempt_count": row.attempt_count,
            "assigned_at": row.assigned_at.isoformat(),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        }
        for row in rows
    ]


async def leave_report(
    session: AsyncSession, *, from_date: date, to_date: date, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.leaves.models import Leave, LeaveType

    stmt = (
        select(Leave, LeaveType.code)
        .join(LeaveType, LeaveType.id == Leave.leave_type_id)
        .where(Leave.start_date <= to_date, Leave.end_date >= from_date)
        .order_by(Leave.start_date)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(Leave.employee_id == employee_id)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "leave_id": str(leave.id),
            "employee_id": str(leave.employee_id),
            "leave_type": code,
            "start_date": leave.start_date.isoformat(),
            "end_date": leave.end_date.isoformat(),
            "total_days": f"{Decimal(leave.total_days):.2f}",
            "status": leave.status,
        }
        for leave, code in rows
    ]


async def ledger_report(
    session: AsyncSession, *, from_date: date, to_date: date, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.payroll.models import EmployeeLedgerEntry

    stmt = (
        select(EmployeeLedgerEntry)
        .where(
            EmployeeLedgerEntry.business_date >= from_date,
            EmployeeLedgerEntry.business_date <= to_date,
        )
        .order_by(EmployeeLedgerEntry.business_date)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(EmployeeLedgerEntry.employee_id == employee_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "id": str(row.id),
            "employee_id": str(row.employee_id),
            "entry_type": row.entry_type,
            "direction": row.direction,
            "amount": money_str(row.amount),
            "currency": row.currency,
            "business_date": row.business_date.isoformat(),
            "reason": row.reason,
        }
        for row in rows
    ]


async def advance_report(
    session: AsyncSession, *, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.payroll.models import Advance

    stmt = select(Advance).order_by(Advance.issued_on.desc()).limit(limit)
    if employee_id:
        stmt = stmt.where(Advance.employee_id == employee_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "id": str(row.id),
            "employee_id": str(row.employee_id),
            "amount": money_str(row.amount),
            "outstanding_amount": money_str(row.outstanding_amount),
            "status": row.status,
            "issued_on": row.issued_on.isoformat(),
        }
        for row in rows
    ]


async def salary_report(
    session: AsyncSession,
    *,
    period_year: int,
    period_month: int,
    employee_id: uuid.UUID | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    from app.modules.payroll.models import SalaryRecord

    stmt = (
        select(SalaryRecord)
        .where(SalaryRecord.period_year == period_year, SalaryRecord.period_month == period_month)
        .order_by(SalaryRecord.employee_id)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(SalaryRecord.employee_id == employee_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "id": str(row.id),
            "employee_id": str(row.employee_id),
            "currency": row.currency,
            "gross_amount": money_str(row.gross_amount),
            "overtime_amount": money_str(row.overtime_amount),
            "bonus_amount": money_str(row.bonus_amount),
            "total_deductions": money_str(row.total_deductions),
            "net_amount": money_str(row.net_amount),
            "status": row.status,
        }
        for row in rows
    ]


async def complaint_report(
    session: AsyncSession,
    *,
    from_date: date,
    to_date: date,
    status: str | None = None,
    category_id: uuid.UUID | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    from app.modules.complaints.models import Complaint

    stmt = (
        select(Complaint)
        .where(func.date(Complaint.created_at) >= from_date, func.date(Complaint.created_at) <= to_date)
        .order_by(Complaint.created_at)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Complaint.status == status)
    if category_id:
        stmt = stmt.where(Complaint.category_id == category_id)
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        {
            "complaint_code": row.complaint_code,
            "status": row.status,
            "priority": row.priority,
            "created_at": row.created_at.isoformat(),
            "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        }
        for row in rows
    ]


async def break_report(
    session: AsyncSession, *, from_date: date, to_date: date, employee_id: uuid.UUID | None = None, limit: int = 5000
) -> list[dict[str, Any]]:
    from app.modules.attendance.models import AttendanceRecord, BreakSession, BreakType

    stmt = (
        select(BreakSession, AttendanceRecord.business_date, BreakType.code, BreakType.is_paid)
        .join(AttendanceRecord, AttendanceRecord.id == BreakSession.attendance_record_id)
        .join(BreakType, BreakType.id == BreakSession.break_type_id)
        .where(AttendanceRecord.business_date >= from_date, AttendanceRecord.business_date <= to_date)
        .order_by(AttendanceRecord.business_date)
        .limit(limit)
    )
    if employee_id:
        stmt = stmt.where(BreakSession.employee_id == employee_id)
    rows = (await session.execute(stmt)).all()
    return [
        {
            "business_date": business_date.isoformat(),
            "employee_id": str(break_row.employee_id),
            "break_type": code,
            "is_paid": is_paid,
            "duration_seconds": break_row.duration_seconds or 0,
        }
        for break_row, business_date, code, is_paid in rows
    ]


async def dashboard_summary(session: AsyncSession, settings: SettingsView, as_of: date | None = None) -> dict[str, Any]:
    from app.modules.attendance.models import AttendanceRecord
    from app.modules.complaints.models import Complaint
    from app.modules.directory.models import Employee
    from app.modules.orders.models import Order
    from app.modules.tasks.models import TaskAssignment

    day = as_of or business_date_of(utcnow(), settings.timezone())
    active_employees = int(
        (
            await session.execute(
                select(func.count()).select_from(Employee).where(Employee.employment_status == "ACTIVE")
            )
        ).scalar_one()
    )
    present_today = int(
        (
            await session.execute(
                select(func.count())
                .select_from(AttendanceRecord)
                .where(AttendanceRecord.business_date == day, AttendanceRecord.status == "PRESENT")
            )
        ).scalar_one()
    )
    open_orders = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.status.in_(["BROADCASTED", "CLAIMED", "PACKING", "PACKED", "READY_FOR_DELIVERY", "OUT_FOR_DELIVERY"]))
            )
        ).scalar_one()
    )
    delivered_today = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.status == "DELIVERED", func.date(Order.delivered_at) == day)
            )
        ).scalar_one()
    )
    open_tasks = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TaskAssignment)
                .where(TaskAssignment.status.in_(["ASSIGNED", "STARTED", "SUBMITTED", "RESUBMISSION_REQUESTED"]))
            )
        ).scalar_one()
    )
    open_complaints = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Complaint)
                .where(Complaint.status.in_(["OPEN", "IN_REVIEW", "ACTION_REQUIRED"]))
            )
        ).scalar_one()
    )
    return {
        "as_of": day.isoformat(),
        "active_employees": active_employees,
        "present_today": present_today,
        "open_orders": open_orders,
        "delivered_today": delivered_today,
        "open_task_assignments": open_tasks,
        "open_complaints": open_complaints,
    }