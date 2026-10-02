"""Directory endpoints (docs/03_API_CONTRACT.md section 5)."""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, or_, select

from app.api.context import Ctx, require, require_any, require_authenticated
from app.api.payloads import build_session_payload
from app.core.errors import NotFound, PermissionDenied, RuleViolation, ValidationError
from app.core.pagination import PageParams, page_params, paginated, parse_sort
from app.core.timeutil import utcnow
from app.modules.directory import service as directory_service
from app.modules.directory.models import Employee, User
from app.modules.rbac import service as rbac_service

router = APIRouter(tags=["directory"])

EMPLOYEE_STATUSES = ("ACTIVE", "INACTIVE", "SUSPENDED", "EXITED")
EMPLOYMENT_TYPES = ("FULL_TIME", "PART_TIME", "CONTRACT")
COMPENSATION_TYPES = ("FIXED_MONTHLY", "DAILY_WAGE", "HOURLY")


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16)) + "!aA1"


class SelfProfileUpdate(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    address_line: str | None = Field(default=None, max_length=500)
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)


class CompensationInput(BaseModel):
    compensation_type: str
    rate: Decimal
    currency: str = Field(min_length=3, max_length=3)
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("compensation_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in COMPENSATION_TYPES:
            raise ValueError(f"Must be one of: {', '.join(COMPENSATION_TYPES)}")
        return value


class EmployeeCreateRequest(BaseModel):
    employee_code: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    date_of_joining: date
    employment_type: str = "FULL_TIME"
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    manager_employee_id: uuid.UUID | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    address_line: str | None = Field(default=None, max_length=500)
    initial_password: str | None = Field(default=None, min_length=8, max_length=512)
    roles: list[str] = Field(default_factory=lambda: ["EMPLOYEE"])
    compensation: CompensationInput | None = None

    @field_validator("employment_type")
    @classmethod
    def _check_type(cls, value: str) -> str:
        if value not in EMPLOYMENT_TYPES:
            raise ValueError(f"Must be one of: {', '.join(EMPLOYMENT_TYPES)}")
        return value


class EmployeeUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    employment_type: str | None = None
    manager_employee_id: uuid.UUID | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=200)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    address_line: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=2000)


class SensitiveUpdateRequest(BaseModel):
    bank_account_name: str | None = Field(default=None, max_length=200)
    bank_account_number: str | None = Field(default=None, max_length=40)
    bank_ifsc: str | None = Field(default=None, max_length=20)
    reason: str = Field(min_length=1, max_length=500)


class DeactivateRequest(BaseModel):
    date_of_exit: date
    reason: str = Field(min_length=1, max_length=500)
    revoke_sessions: bool = True
    force: bool = False


class ReactivateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class RolesUpdateRequest(BaseModel):
    role_codes: list[str]
    reason: str = Field(min_length=1, max_length=500)


def _compensation_payload(row) -> dict:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "compensation_type": row.compensation_type,
        "rate": f"{row.rate:.4f}",
        "currency": row.currency,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to,
        "reason": row.reason,
        "created_at": row.created_at,
    }


@router.get("/me")
async def get_me(ctx: Ctx = Depends(require_authenticated)) -> dict:
    auth = ctx.actor
    user = await directory_service.get_user(ctx.session, auth.user_id)
    return await build_session_payload(
        ctx.session, user=user, settings=ctx.settings, employee_id=auth.employee_id
    )


@router.patch("/me")
async def update_me(
    payload: SelfProfileUpdate, ctx: Ctx = Depends(require("profile.update.self"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, ctx.employee_id)
    changes = payload.model_dump(exclude_unset=True)
    before, after = await directory_service.update_self_profile(ctx.session, employee, changes)
    if before:
        await ctx.audit(
            category="EMPLOYEE",
            action="directory.profile.self_updated",
            entity_type="employee",
            entity_id=employee.id,
            before=before,
            after=after,
        )
    return {"user": {"id": ctx.actor_user_id}, "employee": directory_service.serialize_employee(employee, include_sensitive=False, employee_id=employee.id)}


@router.get("/employees")
async def list_employees(
    status: str | None = Query(None),
    department: str | None = Query(None),
    employment_type: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    sort: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("employee.read.all")),
) -> dict:
    rows, total = await directory_service.list_employees(
        ctx.session,
        status=status,
        department=department,
        employment_type=employment_type,
        q=q,
        offset=params.offset,
        limit=params.page_size,
    )
    include_sensitive = ctx.actor.has("employee.read.sensitive")
    items = [
        directory_service.serialize_employee(
            row, include_sensitive=include_sensitive, employee_id=ctx.actor.employee_id
        )
        for row in rows
    ]
    return paginated(items, total, params)


@router.post("/employees", status_code=201)
async def create_employee(
    payload: EmployeeCreateRequest, ctx: Ctx = Depends(require("employee.create"))
) -> dict:
    generated = None
    password = payload.initial_password
    if password is None:
        password = _generate_password()
        generated = password
    compensation = payload.compensation.model_dump() if payload.compensation else None
    user, employee = await directory_service.create_employee(
        ctx.session,
        employee_code=payload.employee_code,
        full_name=payload.full_name,
        date_of_joining=payload.date_of_joining,
        username=payload.username,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        employment_type=payload.employment_type,
        department=payload.department,
        designation=payload.designation,
        manager_employee_id=payload.manager_employee_id,
        role_codes=payload.roles,
        password=password,
        compensation=compensation,
        created_by=ctx.actor_user_id,
    )
    before_emp = {
        "employee_code": employee.employee_code,
        "full_name": employee.full_name,
        "department": employee.department,
        "designation": employee.designation,
    }
    for field in (
        "emergency_contact_name",
        "emergency_contact_phone",
        "address_line",
    ):
        value = getattr(payload, field)
        if value:
            setattr(employee, field, value.strip())
    await ctx.session.flush()
    await ctx.audit(
        category="EMPLOYEE",
        action="directory.employee.created",
        entity_type="employee",
        entity_id=employee.id,
        after=before_emp,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "directory.employee.created.v1",
        aggregate_type="employee",
        aggregate_id=employee.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_code": employee.employee_code},
    )
    result = directory_service.serialize_employee(
        employee, include_sensitive=True, employee_id=employee.id
    )
    result["user"] = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "status": user.status,
        "must_change_password": user.must_change_password,
    }
    if generated is not None:
        result["initial_password"] = generated
    return result


async def _load_employee(ctx: Ctx, employee_id: uuid.UUID) -> Employee:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    if ctx.actor.has("employee.read.all") or employee.id == ctx.actor.employee_id:
        return employee
    raise NotFound("Employee not found.")


@router.get("/employees/{employee_id}")
async def get_employee(employee_id: uuid.UUID, ctx: Ctx = Depends(require_any("employee.read.all", "employee.read.self"))) -> dict:
    employee = await _load_employee(ctx, employee_id)
    return directory_service.serialize_employee(
        employee,
        include_sensitive=ctx.actor.has("employee.read.sensitive"),
        employee_id=ctx.actor.employee_id,
    )


@router.patch("/employees/{employee_id}")
async def update_employee(
    employee_id: uuid.UUID, payload: EmployeeUpdateRequest, ctx: Ctx = Depends(require("employee.update"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = str(changes["email"])
    before, after = await directory_service.update_employee(ctx.session, employee, changes)
    if before:
        await ctx.audit(
            category="EMPLOYEE",
            action="directory.employee.updated",
            entity_type="employee",
            entity_id=employee.id,
            before=before,
            after=after,
        )
    return directory_service.serialize_employee(
        employee, include_sensitive=ctx.actor.has("employee.read.sensitive"), employee_id=ctx.actor.employee_id
    )


@router.patch("/employees/{employee_id}/sensitive")
async def update_sensitive(
    employee_id: uuid.UUID, payload: SensitiveUpdateRequest, ctx: Ctx = Depends(require("employee.update.sensitive"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    before, after = await directory_service.update_sensitive_fields(ctx.session, employee, changes)
    if before:
        await ctx.audit(
            category="EMPLOYEE",
            action="directory.employee.sensitive_updated",
            entity_type="employee",
            entity_id=employee.id,
            before=before,
            after=after,
            reason=payload.reason,
        )
    return {
        "employee_id": employee.id,
        "bank_account_name": employee.bank_account_name,
        "bank_account_number": directory_service.mask_account_number(employee.bank_account_number),
        "bank_ifsc": employee.bank_ifsc,
    }


@router.post("/employees/{employee_id}/deactivate")
async def deactivate_employee(
    employee_id: uuid.UUID, payload: DeactivateRequest, ctx: Ctx = Depends(require("employee.deactivate"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    if ctx.actor.employee_id == employee.id:
        raise RuleViolation("You cannot deactivate your own account.", rule_code="SELF_DEACTIVATION")
    open_work = await _open_work_counts(ctx, employee.id)
    if any(open_work.values()) and not payload.force:
        raise RuleViolation(
            "The employee holds open orders or tasks; reassign them or set force=true.",
            rule_code="OPEN_WORK_PRESENT",
            extra={"open_work": open_work},
        )
    before = await directory_service.deactivate_employee(
        ctx.session, employee, date_of_exit=payload.date_of_exit, reason=payload.reason
    )
    if payload.revoke_sessions:
        from app.modules.identity import service as identity_service

        await identity_service.revoke_all_sessions(
            ctx.session, employee.user_id, reason="EMPLOYEE_DEACTIVATED"
        )
    await ctx.audit(
        category="EMPLOYEE",
        action="directory.employee.deactivated",
        entity_type="employee",
        entity_id=employee.id,
        before=before,
        after={"employment_status": "EXITED", "date_of_exit": str(payload.date_of_exit)},
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "directory.employee.deactivated.v1",
        aggregate_type="employee",
        aggregate_id=employee.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_code": employee.employee_code, "reason": payload.reason},
    )
    return directory_service.serialize_employee(
        employee, include_sensitive=ctx.actor.has("employee.read.sensitive"), employee_id=ctx.actor.employee_id
    )


async def _open_work_counts(ctx: Ctx, employee_id: uuid.UUID) -> dict[str, int]:
    from app.modules.orders import service as order_service
    from app.modules.tasks import service as task_service

    return {
        "active_order_claims": await order_service.count_active_claims(ctx.session, employee_id),
        "open_task_assignments": await task_service.count_open_assignments(ctx.session, employee_id),
    }


@router.post("/employees/{employee_id}/reactivate")
async def reactivate_employee(
    employee_id: uuid.UUID, payload: ReactivateRequest, ctx: Ctx = Depends(require("employee.deactivate"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    before = await directory_service.reactivate_employee(ctx.session, employee)
    await ctx.audit(
        category="EMPLOYEE",
        action="directory.employee.reactivated",
        entity_type="employee",
        entity_id=employee.id,
        before=before,
        after={"employment_status": "ACTIVE"},
        reason=payload.reason,
    )
    return directory_service.serialize_employee(employee, include_sensitive=True, employee_id=employee.id)


@router.get("/employees/{employee_id}/compensation")
async def list_compensation(
    employee_id: uuid.UUID, ctx: Ctx = Depends(require("employee.read.sensitive"))
) -> dict:
    await directory_service.get_employee(ctx.session, employee_id)
    rows = await directory_service.list_compensation(ctx.session, employee_id)
    return {"items": [_compensation_payload(row) for row in rows]}


@router.post("/employees/{employee_id}/compensation", status_code=201)
async def create_compensation(
    employee_id: uuid.UUID, payload: CompensationInput, ctx: Ctx = Depends(require("employee.update.sensitive"))
) -> dict:
    employee = await directory_service.get_employee(ctx.session, employee_id)
    row = await directory_service.add_compensation(
        ctx.session,
        employee=employee,
        compensation_type=payload.compensation_type,
        rate=payload.rate,
        currency=payload.currency.upper(),
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        reason=payload.reason,
        created_by=ctx.actor_user_id,
    )
    await ctx.audit(
        category="FINANCIAL",
        action="directory.compensation.created",
        entity_type="employee_compensation",
        entity_id=row.id,
        after={
            "employee_id": str(employee.id),
            "compensation_type": row.compensation_type,
            "rate": f"{row.rate:.4f}",
            "effective_from": str(row.effective_from),
        },
        reason=payload.reason,
    )
    return _compensation_payload(row)


@router.put("/users/{user_id}/roles")
async def set_user_roles(
    user_id: uuid.UUID, payload: RolesUpdateRequest, ctx: Ctx = Depends(require("employee.manage.roles"))
) -> dict:
    user = await directory_service.get_user(ctx.session, user_id)
    if user.id == ctx.actor_user_id and rbac_service.ADMIN_ROLE_CODE in ctx.actor.roles:
        if rbac_service.ADMIN_ROLE_CODE not in [code.upper() for code in payload.role_codes]:
            raise RuleViolation(
                "Administrators cannot remove their own admin role.", rule_code="SELF_ESCALATION"
            )
    before = list(ctx.actor.roles) if user.id == ctx.actor_user_id else None
    if user.id != ctx.actor_user_id:
        access = await rbac_service.effective_access(ctx.session, user.id)
        before = list(access.roles)
    if rbac_service.ADMIN_ROLE_CODE in (before or []) and rbac_service.ADMIN_ROLE_CODE not in [
        code.upper() for code in payload.role_codes
    ]:
        await _assert_not_last_admin(ctx, user.id)
    roles = await rbac_service.assign_roles(
        ctx.session, user.id, [code.upper() for code in payload.role_codes], actor_user_id=ctx.actor_user_id
    )
    await ctx.audit(
        category="PERMISSION",
        action="directory.user.roles_changed",
        entity_type="user",
        entity_id=user.id,
        before={"roles": before},
        after={"roles": roles},
        reason=payload.reason,
    )
    return {"user_id": user.id, "roles": roles}


async def _assert_not_last_admin(ctx: Ctx, user_id: uuid.UUID) -> None:
    admin_role = await rbac_service.get_role_by_code(ctx.session, rbac_service.ADMIN_ROLE_CODE)
    from app.modules.rbac.models import UserRole

    count = int(
        (
            await ctx.session.execute(
                select(func.count()).select_from(UserRole).where(UserRole.role_id == admin_role.id)
            )
        ).scalar_one()
    )
    holders = (
        await ctx.session.execute(
            select(UserRole.user_id).where(UserRole.role_id == admin_role.id)
        )
    ).scalars().all()
    if count <= 1 and user_id in holders:
        raise RuleViolation(
            "At least one administrator must retain the ADMIN role.", rule_code="LAST_ADMIN"
        )


@router.get("/users")
async def list_users(
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("employee.read.all")),
) -> dict:
    conditions = []
    if status:
        conditions.append(User.status == status)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            or_(func.lower(User.username).like(pattern), func.lower(User.email).like(pattern))
        )
    stmt = select(User).order_by(User.username)
    count_stmt = select(func.count()).select_from(User)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = int((await ctx.session.execute(count_stmt)).scalar_one())
    rows = list(
        (await ctx.session.execute(stmt.offset(params.offset).limit(params.page_size))).scalars().all()
    )
    items = [
        {
            "id": row.id,
            "username": row.username,
            "email": row.email,
            "status": row.status,
            "last_login_at": row.last_login_at,
            "must_change_password": row.must_change_password,
            "created_at": row.created_at,
        }
        for row in rows
    ]
    return paginated(items, total, params)