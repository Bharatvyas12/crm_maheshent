"""Directory tables (docs/02_DATABASE.md sections 4.1, 6.1, 6.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ExcludeConstraint, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import created_at_col, uuid_pk

STATUS_VALUES = "('ACTIVE','DISABLED','LOCKED')"
EMPLOYMENT_STATUS = "('ACTIVE','INACTIVE','SUSPENDED','EXITED')"
EMPLOYMENT_TYPE = "('FULL_TIME','PART_TIME','CONTRACT')"
COMPENSATION_TYPE = "('FIXED_MONTHLY','DAILY_WAGE','HOURLY')"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ACTIVE'")
    )
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(f"status IN {STATUS_VALUES}", name="ck_users_status"),
        CheckConstraint("failed_login_count >= 0", name="ck_users_failed_login_count"),
        Index("ix_users_status", "status"),
    )


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True
    )
    employee_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    date_of_joining: Mapped[date] = mapped_column(Date, nullable=False)
    date_of_exit: Mapped[date | None] = mapped_column(Date)
    employment_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ACTIVE'")
    )
    employment_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'FULL_TIME'")
    )
    department: Mapped[str | None] = mapped_column(Text)
    designation: Mapped[str | None] = mapped_column(Text)
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    emergency_contact_name: Mapped[str | None] = mapped_column(Text)
    emergency_contact_phone: Mapped[str | None] = mapped_column(Text)
    address_line: Mapped[str | None] = mapped_column(Text)
    bank_account_name: Mapped[str | None] = mapped_column(Text)
    bank_account_number: Mapped[str | None] = mapped_column(Text)
    bank_ifsc: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))

    __table_args__ = (
        CheckConstraint(
            f"employment_status IN {EMPLOYMENT_STATUS}", name="ck_employees_status"
        ),
        CheckConstraint(
            f"employment_type IN {EMPLOYMENT_TYPE}", name="ck_employees_employment_type"
        ),
        CheckConstraint(
            "manager_employee_id IS NULL OR manager_employee_id <> id",
            name="ck_employees_manager_not_self",
        ),
        CheckConstraint(
            "date_of_exit IS NULL OR date_of_exit >= date_of_joining",
            name="ck_employees_exit_after_joining",
        ),
        Index("ix_employees_status", "employment_status"),
        Index("ix_employees_department", "department"),
    )


class EmployeeCompensation(Base):
    __tablename__ = "employee_compensation"

    id: Mapped[uuid.UUID] = uuid_pk()
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    compensation_type: Mapped[str] = mapped_column(Text, nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            f"compensation_type IN {COMPENSATION_TYPE}",
            name="ck_employee_compensation_type",
        ),
        CheckConstraint("rate > 0", name="ck_employee_compensation_rate_positive"),
        CheckConstraint("char_length(currency) = 3", name="ck_employee_compensation_currency"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_employee_compensation_period",
        ),
        ExcludeConstraint(
            ("employee_id", "="),
            (text("daterange(effective_from, COALESCE(effective_to, 'infinity'::date), '[]')"), "&&"),
            using="gist",
            name="ex_employee_compensation_no_overlap",
        ),
        Index(
            "ix_employee_compensation_employee_from",
            "employee_id",
            text("effective_from DESC"),
        ),
    )