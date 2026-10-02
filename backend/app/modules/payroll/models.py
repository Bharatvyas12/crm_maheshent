"""Payroll tables (docs/02_DATABASE.md section 13). Money is Decimal/numeric only."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import created_at_col, money_col, uuid_pk, version_col

ENTRY_TYPE = (
    "('SALARY_PAYABLE','OVERTIME_PAY','BONUS','ADJUSTMENT','ADVANCE_ISSUED','ADVANCE_REPAYMENT',"
    "'LEAVE_DEDUCTION','LATE_DEDUCTION','OTHER_DEDUCTION','PAYMENT_MADE','REVERSAL')"
)
DIRECTION = "('CREDIT','DEBIT')"
REPAYMENT_MODE = "('LUMP_SUM','INSTALLMENTS')"
ADVANCE_STATUS = "('PENDING_APPROVAL','OUTSTANDING','PARTIALLY_REPAID','CLOSED','WRITTEN_OFF','CANCELLED')"
INSTALLMENT_STATUS = "('PENDING','PARTIALLY_RECOVERED','RECOVERED','SKIPPED')"
RUN_STATUS = "('DRAFT','COMPUTED','FINALIZED','LOCKED','PAID','CANCELLED')"
SALARY_STATUS = "('DRAFT','FINALIZED','PAID')"
SNAPSHOT_SCOPE = "('GLOBAL','EMPLOYEE')"
COMPENSATION_TYPE = "('FIXED_MONTHLY','DAILY_WAGE','HOURLY')"


class EmployeeLedgerEntry(Base):
    __tablename__ = "employee_ledger_entries"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_year: Mapped[int | None] = mapped_column(Integer)
    period_month: Mapped[int | None] = mapped_column(Integer)
    salary_record_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salary_records.id", name="fk_ledger_salary_record")
    )
    advance_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("advances.id")
    )
    payroll_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id")
    )
    reference_type: Mapped[str | None] = mapped_column(Text)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_ledger_entries.id")
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"entry_type IN {ENTRY_TYPE}", name="ck_ledger_entry_type"),
        CheckConstraint(f"direction IN {DIRECTION}", name="ck_ledger_direction"),
        CheckConstraint("amount > 0", name="ck_ledger_amount_positive"),
        CheckConstraint(
            "period_month IS NULL OR period_month BETWEEN 1 AND 12", name="ck_ledger_period_month"
        ),
        Index("ix_ledger_employee_date", "employee_id", text("business_date DESC")),
        Index("ix_ledger_period", "period_year", "period_month"),
        Index("ix_ledger_type", "entry_type"),
        Index("ix_ledger_salary_record", "salary_record_id"),
        Index("ix_ledger_advance", "advance_id"),
    )


class Advance(Base):
    __tablename__ = "advances"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    repayment_mode: Mapped[str] = mapped_column(Text, nullable=False)
    installment_count: Mapped[int | None] = mapped_column(Integer)
    installment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    outstanding_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OUTSTANDING'"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_advances_amount_positive"),
        CheckConstraint("outstanding_amount >= 0", name="ck_advances_outstanding_non_negative"),
        CheckConstraint("outstanding_amount <= amount", name="ck_advances_outstanding_le_amount"),
        CheckConstraint(f"repayment_mode IN {REPAYMENT_MODE}", name="ck_advances_repayment_mode"),
        CheckConstraint(f"status IN {ADVANCE_STATUS}", name="ck_advances_status"),
        CheckConstraint(
            "installment_count IS NULL OR installment_count > 0", name="ck_advances_installment_count"
        ),
        CheckConstraint(
            "installment_amount IS NULL OR installment_amount > 0", name="ck_advances_installment_amount"
        ),
        CheckConstraint(
            "repayment_mode <> 'INSTALLMENTS'"
            " OR (installment_count IS NOT NULL AND installment_amount IS NOT NULL)",
            name="ck_advances_installments_required",
        ),
        Index("ix_advances_employee_status", "employee_id", "status"),
        Index("ix_advances_status_issued", "status", "issued_on"),
    )


class AdvanceInstallment(Base):
    __tablename__ = "advance_installments"

    id: Mapped[uuid.UUID] = uuid_pk()
    advance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("advances.id"), nullable=False
    )
    installment_no: Mapped[int] = mapped_column(Integer, nullable=False)
    due_period_year: Mapped[int | None] = mapped_column(Integer)
    due_period_month: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recovered_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, server_default=text("0")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_ledger_entries.id", name="fk_salary_records_ledger_entry")
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("advance_id", "installment_no", name="uq_advance_installments_advance_no"),
        CheckConstraint("installment_no >= 1", name="ck_advance_installments_no"),
        CheckConstraint("amount > 0", name="ck_advance_installments_amount"),
        CheckConstraint("recovered_amount >= 0", name="ck_advance_installments_recovered_non_negative"),
        CheckConstraint("recovered_amount <= amount", name="ck_advance_installments_recovered_le_amount"),
        CheckConstraint(f"status IN {INSTALLMENT_STATUS}", name="ck_advance_installments_status"),
        CheckConstraint(
            "due_period_month IS NULL OR due_period_month BETWEEN 1 AND 12",
            name="ck_advance_installments_due_month",
        ),
        Index("ix_advance_installments_due_period", "due_period_year", "due_period_month", "status"),
    )


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("period_year", "period_month", name="uq_payroll_runs_period"),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_payroll_runs_month"),
        CheckConstraint(f"status IN {RUN_STATUS}", name="ck_payroll_runs_status"),
    )


class PayrollRuleSnapshot(Base):
    __tablename__ = "payroll_rule_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    payroll_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id")
    )
    salary_record_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    settings_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    settings_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"scope IN {SNAPSHOT_SCOPE}", name="ck_payroll_rule_snapshots_scope"),
        Index("ix_payroll_rule_snapshots_hash", "settings_hash"),
        Index("ix_payroll_rule_snapshots_run", "payroll_run_id"),
    )


class SalaryRecord(Base):
    __tablename__ = "salary_records"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_runs.id"), nullable=False
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    compensation_type: Mapped[str] = mapped_column(Text, nullable=False)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    present_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    leave_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    absent_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    half_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    weekly_off_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    holiday_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    payable_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default=text("0"))
    worked_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    overtime_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    gross_amount: Mapped[Decimal] = money_col(default="0")
    overtime_amount: Mapped[Decimal] = money_col(default="0")
    bonus_amount: Mapped[Decimal] = money_col(default="0")
    leave_deduction: Mapped[Decimal] = money_col(default="0")
    late_deduction: Mapped[Decimal] = money_col(default="0")
    advance_deduction: Mapped[Decimal] = money_col(default="0")
    other_deduction: Mapped[Decimal] = money_col(default="0")
    total_deductions: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        Computed(
            "leave_deduction + late_deduction + advance_deduction + other_deduction",
            persisted=True,
        ),
    )
    net_amount: Mapped[Decimal] = money_col(default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'DRAFT'"))
    inputs_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False)
    calculation_breakdown: Mapped[Any] = mapped_column(JSONB, nullable=False)
    rule_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payroll_rule_snapshots.id"), nullable=False
    )
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    computed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employee_ledger_entries.id")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "period_year", "period_month", name="uq_salary_records_employee_period"
        ),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_salary_records_month"),
        CheckConstraint(f"compensation_type IN {COMPENSATION_TYPE}", name="ck_salary_records_compensation_type"),
        CheckConstraint("base_rate >= 0", name="ck_salary_records_base_rate"),
        CheckConstraint(f"status IN {SALARY_STATUS}", name="ck_salary_records_status"),
        CheckConstraint(
            "net_amount = gross_amount + overtime_amount + bonus_amount - total_deductions",
            name="ck_salary_records_net_identity",
        ),
        CheckConstraint(
            "status = 'DRAFT' OR (finalized_by IS NOT NULL AND finalized_at IS NOT NULL)",
            name="ck_salary_records_finalized",
        ),
        Index("ix_salary_records_run_status", "payroll_run_id", "status"),
        Index("ix_salary_records_period", "period_year", "period_month"),
    )