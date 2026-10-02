"""Leave tables (docs/02_DATABASE.md section 12)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bool_false, bool_true, created_at_col, uuid_pk, version_col

LEAVE_STATUS = "('PENDING','APPROVED','REJECTED','CANCELLED','MODIFICATION_REQUESTED')"
HALF_DAY_PERIOD = "('FIRST_HALF','SECOND_HALF')"
ACCRUAL_MODE = "('ANNUAL_UPFRONT','MONTHLY_ACCRUAL','MANUAL')"
MOVEMENT_TYPE = (
    "('ACCRUAL','ALLOCATION','CARRY_FORWARD','EXPIRY','ADJUSTMENT','PENDING_HOLD',"
    "'PENDING_RELEASE','USAGE','REVERSAL')"
)


class LeaveType(Base):
    __tablename__ = "leave_types"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_paid: Mapped[bool] = bool_true()
    requires_approval: Mapped[bool] = bool_true()
    requires_attachment_after_days: Mapped[int | None] = mapped_column(Integer)
    max_consecutive_days: Mapped[int | None] = mapped_column(Integer)
    allow_half_day: Mapped[bool] = bool_false()
    annual_entitlement_days: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    accrual_mode: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = bool_true()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(
            "requires_attachment_after_days IS NULL OR requires_attachment_after_days > 0",
            name="ck_leave_types_attachment_days",
        ),
        CheckConstraint(
            "max_consecutive_days IS NULL OR max_consecutive_days > 0",
            name="ck_leave_types_max_consecutive",
        ),
        CheckConstraint(
            "annual_entitlement_days IS NULL OR annual_entitlement_days >= 0",
            name="ck_leave_types_entitlement",
        ),
        CheckConstraint(
            f"accrual_mode IS NULL OR accrual_mode IN {ACCRUAL_MODE}", name="ck_leave_types_accrual_mode"
        ),
    )


class Leave(Base):
    __tablename__ = "leaves"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_half_day: Mapped[bool] = bool_false()
    half_day_period: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_file_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    balance_pending_hold_applied: Mapped[bool] = bool_false()
    balance_usage_applied: Mapped[bool] = bool_false()
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_leaves_date_order"),
        CheckConstraint("total_days > 0", name="ck_leaves_total_days"),
        CheckConstraint(f"status IN {LEAVE_STATUS}", name="ck_leaves_status"),
        CheckConstraint(
            f"half_day_period IS NULL OR half_day_period IN {HALF_DAY_PERIOD}",
            name="ck_leaves_half_day_period",
        ),
        CheckConstraint(
            "(is_half_day = false AND half_day_period IS NULL)"
            " OR (is_half_day = true AND half_day_period IS NOT NULL AND start_date = end_date)",
            name="ck_leaves_half_day_shape",
        ),
        CheckConstraint(
            "status <> 'APPROVED' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_leaves_decided",
        ),
        ExcludeConstraint(
            ("employee_id", "="),
            (text("daterange(start_date, end_date, '[]')"), "&&"),
            using="gist",
            name="ex_leaves_no_overlap",
            where=text("status IN ('PENDING','APPROVED')"),
        ),
        Index("ix_leaves_employee_start", "employee_id", text("start_date DESC")),
        Index("ix_leaves_status_applied", "status", "applied_at"),
        Index("ix_leaves_type_start", "leave_type_id", "start_date"),
    )


class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    entitled_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    accrued_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    carried_forward_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    adjustment_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    used_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    pending_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, server_default=text("0")
    )
    available_days: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        Computed(
            "entitled_days + accrued_days + carried_forward_days + adjustment_days"
            " - used_days - pending_days",
            persisted=True,
        ),
    )
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "leave_type_id", "period_year", name="uq_leave_balances_employee_type_year"
        ),
        CheckConstraint("period_year BETWEEN 2000 AND 2200", name="ck_leave_balances_year"),
        CheckConstraint("entitled_days >= 0", name="ck_leave_balances_entitled"),
        CheckConstraint("accrued_days >= 0", name="ck_leave_balances_accrued"),
        CheckConstraint("carried_forward_days >= 0", name="ck_leave_balances_carried"),
        CheckConstraint("used_days >= 0", name="ck_leave_balances_used"),
        CheckConstraint("pending_days >= 0", name="ck_leave_balances_pending"),
    )


class LeaveBalanceLedger(Base):
    __tablename__ = "leave_balance_ledger"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_type: Mapped[str] = mapped_column(Text, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    leave_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("leaves.id"))
    reference_type: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("leave_balance_ledger.id")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"movement_type IN {MOVEMENT_TYPE}", name="ck_leave_balance_ledger_type"),
        Index(
            "ix_leave_balance_ledger_employee_type_year",
            "employee_id",
            "leave_type_id",
            "period_year",
            "created_at",
        ),
        Index("ix_leave_balance_ledger_leave", "leave_id"),
    )