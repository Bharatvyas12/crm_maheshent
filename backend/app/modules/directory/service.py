"""Directory service: users, employees, compensation and self-service profile."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DuplicateConflict, NotFound, RuleViolation, ValidationError
from app.core.money import quantize_rate
from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.modules.directory.models import Employee, EmployeeCompensation, User

SELF_EDITABLE_FIELDS = (
    "phone",
    "email",
    "emergency_contact_name",
    "emergency_contact_phone",
    "address_line",
)

ADMIN_EDITABLE_FIELDS = (
    "full_name",
    "phone",
    "email",
    "department",
    "designation",
    "employment_type",
    "manager_employee_id",
    "emergency_contact_name",
    "emergency_contact_phone",
    "address_line",
    "notes",
)

SENSITIVE_FIELDS = ("bank_account_name", "bank_account_number", "bank_ifsc")


def mask_account_number(number: str | None) -> str | None:
    if not number:
        return number
    digits = re.sub(r"\s+", "", number)
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


def serialize_employee(
    employee: Employee, *, include_sensitive: bool, employee_id: uuid.UUID | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": employee.id,
        "user_id": employee.user_id,
        "employee_code": employee.employee_code,
        "full_name": employee.full_name,
        "phone": employee.phone,
        "email": employee.email,
        "date_of_joining": employee.date_of_joining,
        "date_of_exit": employee.date_of_exit,
        "employment_status": employee.employment_status,
        "employment_type": employee.employment_type,
        "department": employee.department,
        "designation": employee.designation,
        "manager_employee_id": employee.manager_employee_id,
        "emergency_contact_name": employee.emergency_contact_name,
        "emergency_contact_phone": employee.emergency_contact_phone,
        "address_line": employee.address_line,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }
    if include_sensitive:
        payload["bank_account_name"] = employee.bank_account_name
        payload["bank_account_number"] = employee.bank_account_number
        payload["bank_ifsc"] = employee.bank_ifsc
    elif employee_id is not None and employee_id == employee.id:
        payload["bank_account_name"] = employee.bank_account_name
        payload["bank_account_number"] = mask_account_number(employee.bank_account_number)
        payload["bank_ifsc"] = employee.bank_ifsc
    return payload


async def get_employee(session: AsyncSession, employee_id: uuid.UUID) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise NotFound("Employee not found.")
    return employee


async def get_employee_by_user_id(session: AsyncSession, user_id: uuid.UUID) -> Employee | None:
    return (
        await session.execute(select(Employee).where(Employee.user_id == user_id))
    ).scalar_one_or_none()


async def employee_id_for_user(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    return (
        await session.execute(select(Employee.id).where(Employee.user_id == user_id))
    ).scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found.")
    return user


async def resolve_employee(session: AsyncSession, employee_id: uuid.UUID) -> Employee:
    return await get_employee(session, employee_id)


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


async def create_employee(
    session: AsyncSession,
    *,
    employee_code: str,
    full_name: str,
    date_of_joining: date,
    username: str | None,
    email: str | None,
    phone: str | None,
    employment_type: str = "FULL_TIME",
    department: str | None = None,
    designation: str | None = None,
    manager_employee_id: uuid.UUID | None = None,
    role_codes: list[str] | None = None,
    password: str | None = None,
    compensation: dict[str, Any] | None = None,
    created_by: uuid.UUID | None = None,
) -> tuple[User, Employee]:
    employee_code = (employee_code or "").strip()
    if not employee_code:
        raise ValidationError(
            "employee_code is required.",
            errors=[{"field": "employee_code", "code": "REQUIRED", "message": "Required"}],
        )
    if await _employee_code_exists(session, employee_code):
        raise DuplicateConflict(f"Employee code {employee_code} already exists.")
    derived_username = (username or employee_code).strip().lower()
    if await _username_exists(session, derived_username):
        raise DuplicateConflict(f"Username {derived_username} already exists.")
    if email and await _email_exists(session, email):
        raise DuplicateConflict(f"Email {email} already exists.")
    if manager_employee_id is not None:
        await get_employee(session, manager_employee_id)

    user = User(
        username=derived_username,
        email=_clean(email),
        password_hash=hash_password(password or employee_code),
        status="ACTIVE",
        must_change_password=True,
    )
    session.add(user)
    await session.flush()
    employee = Employee(
        user_id=user.id,
        employee_code=employee_code,
        full_name=full_name.strip(),
        phone=_clean(phone),
        email=_clean(email),
        date_of_joining=date_of_joining,
        employment_type=employment_type,
        department=_clean(department),
        designation=_clean(designation),
        manager_employee_id=manager_employee_id,
        created_by=created_by,
    )
    session.add(employee)
    await session.flush()

    from app.modules.rbac import service as rbac_service

    await rbac_service.assign_roles(
        session, user.id, role_codes or [rbac_service.EMPLOYEE_ROLE_CODE], actor_user_id=created_by
    )
    if compensation:
        await add_compensation(
            session, employee=employee, actor_user_id=created_by, **compensation
        )
    return user, employee


async def _employee_code_exists(session: AsyncSession, code: str) -> bool:
    return bool(
        (
            await session.execute(select(Employee.id).where(Employee.employee_code == code))
        ).scalar_one_or_none()
    )


async def _username_exists(session: AsyncSession, username: str) -> bool:
    return bool(
        (
            await session.execute(select(User.id).where(User.username == username))
        ).scalar_one_or_none()
    )


async def _email_exists(session: AsyncSession, email: str) -> bool:
    return bool(
        (await session.execute(select(User.id).where(User.email == email))).scalar_one_or_none()
    )

async def update_employee(
    session: AsyncSession, employee: Employee, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ADMIN_EDITABLE_FIELDS:
        if field not in changes:
            continue
        value = changes[field]
        if field == "email" and value:
            other = (
                await session.execute(
                    select(User.id).where(User.email == value, User.id != employee.user_id)
                )
            ).scalar_one_or_none()
            if other:
                raise DuplicateConflict(f"Email {value} is already in use.")
        if field == "manager_employee_id" and value is not None:
            if value == employee.id:
                raise RuleViolation("An employee cannot be their own manager.")
            await get_employee(session, value)
        if field in ("full_name",):
            if not str(value).strip():
                raise ValidationError(
                    "full_name cannot be empty.",
                    errors=[{"field": "full_name", "code": "REQUIRED", "message": "Required"}],
                )
        before[field] = getattr(employee, field)
        new_value = _clean(value) if isinstance(value, str) else value
        setattr(employee, field, new_value)
        after[field] = new_value
    if not before:
        return before, after
    employee.updated_at = utcnow()
    user = await session.get(User, employee.user_id)
    if user is not None and "email" in changes:
        user.email = _clean(changes["email"])
    await session.flush()
    return before, after


async def update_sensitive_fields(
    session: AsyncSession, employee: Employee, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in SENSITIVE_FIELDS:
        if field not in changes:
            continue
        before[field] = getattr(employee, field)
        new_value = _clean(changes[field])
        setattr(employee, field, new_value)
        after[field] = new_value
    employee.updated_at = utcnow()
    await session.flush()
    return before, after


async def deactivate_employee(
    session: AsyncSession,
    employee: Employee,
    *,
    date_of_exit: date,
    reason: str,
) -> dict[str, Any]:
    if employee.employment_status == "EXITED":
        raise RuleViolation("Employee has already exited.", rule_code="ALREADY_EXITED")
    if date_of_exit < employee.date_of_joining:
        raise ValidationError("date_of_exit cannot precede the joining date.")
    before = {
        "employment_status": employee.employment_status,
        "date_of_exit": employee.date_of_exit,
    }
    employee.employment_status = "EXITED"
    employee.date_of_exit = date_of_exit
    employee.updated_at = utcnow()
    user = await session.get(User, employee.user_id)
    if user is not None:
        user.status = "DISABLED"
    await session.flush()
    return before


async def reactivate_employee(session: AsyncSession, employee: Employee) -> dict[str, Any]:
    if employee.employment_status == "ACTIVE":
        raise RuleViolation("Employee is already active.")
    before = {"employment_status": employee.employment_status, "date_of_exit": employee.date_of_exit}
    employee.employment_status = "ACTIVE"
    employee.date_of_exit = None
    employee.updated_at = utcnow()
    user = await session.get(User, employee.user_id)
    if user is not None and user.status == "DISABLED":
        user.status = "ACTIVE"
    await session.flush()
    return before


async def add_compensation(
    session: AsyncSession,
    *,
    employee: Employee,
    compensation_type: str,
    rate: Decimal | str,
    currency: str,
    effective_from: date,
    effective_to: date | None = None,
    reason: str,
    created_by: uuid.UUID | None,
) -> EmployeeCompensation:
    decimal_rate = quantize_rate(rate)
    if decimal_rate <= 0:
        raise ValidationError("Compensation rate must be greater than zero.")
    overlapping = (
        await session.execute(
            select(EmployeeCompensation.id).where(
                EmployeeCompensation.employee_id == employee.id,
                EmployeeCompensation.effective_from <= (effective_to or date(9999, 12, 31)),
                or_(
                    EmployeeCompensation.effective_to.is_(None),
                    EmployeeCompensation.effective_to >= effective_from,
                ),
            )
        )
    ).scalar_one_or_none()
    if overlapping:
        raise RuleViolation(
            "A compensation period already exists that overlaps this range.",
            rule_code="COMPENSATION_OVERLAP",
        )
    row = EmployeeCompensation(
        employee_id=employee.id,
        compensation_type=compensation_type,
        rate=decimal_rate,
        currency=currency,
        effective_from=effective_from,
        effective_to=effective_to,
        reason=reason,
        created_by=created_by or employee.user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def current_compensation(
    session: AsyncSession, employee_id: uuid.UUID, on_date: date | None = None
) -> EmployeeCompensation | None:
    target = on_date or utcnow().date()
    return (
        await session.execute(
            select(EmployeeCompensation)
            .where(
                EmployeeCompensation.employee_id == employee_id,
                EmployeeCompensation.effective_from <= target,
                or_(
                    EmployeeCompensation.effective_to.is_(None),
                    EmployeeCompensation.effective_to >= target,
                ),
            )
            .order_by(EmployeeCompensation.effective_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def list_compensation(
    session: AsyncSession, employee_id: uuid.UUID
) -> list[EmployeeCompensation]:
    return list(
        (
            await session.execute(
                select(EmployeeCompensation)
                .where(EmployeeCompensation.employee_id == employee_id)
                .order_by(EmployeeCompensation.effective_from.desc())
            )
        ).scalars().all()
    )


async def update_self_profile(
    session: AsyncSession, employee: Employee, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in SELF_EDITABLE_FIELDS:
        if field not in changes:
            continue
        before[field] = getattr(employee, field)
        new_value = _clean(changes[field])
        setattr(employee, field, new_value)
        after[field] = new_value
    employee.updated_at = utcnow()
    await session.flush()
    return before, after


async def list_employees(
    session: AsyncSession,
    *,
    status: str | None = None,
    department: str | None = None,
    employment_type: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Employee], int]:
    conditions = []
    if status:
        conditions.append(Employee.employment_status == status)
    if department:
        conditions.append(Employee.department == department)
    if employment_type:
        conditions.append(Employee.employment_type == employment_type)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Employee.full_name).like(pattern),
                func.lower(Employee.employee_code).like(pattern),
            )
        )
    count_stmt = select(func.count()).select_from(Employee)
    stmt = select(Employee).order_by(Employee.employee_code)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
        stmt = stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


@dataclass(slots=True)
class EmployeeSummary:
    id: uuid.UUID
    employee_code: str
    full_name: str
    employment_status: str


async def summarize_employees(
    session: AsyncSession, employee_ids: list[uuid.UUID]
) -> dict[uuid.UUID, EmployeeSummary]:
    if not employee_ids:
        return {}
    rows = (
        await session.execute(
            select(Employee.id, Employee.employee_code, Employee.full_name, Employee.employment_status)
            .where(Employee.id.in_(employee_ids))
        )
    ).all()
    return {
        row[0]: EmployeeSummary(
            id=row[0], employee_code=row[1], full_name=row[2], employment_status=row[3]
        )
        for row in rows
    }