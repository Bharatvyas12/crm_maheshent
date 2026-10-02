"""Idempotent reference-data seeding (roles, permissions, settings, lookups).

Used by `scripts/seed.py` and `scripts/create_admin.py`, and by the test suite.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import ALL_PERMISSION_CODES, EMPLOYEE_PERMISSION_CODES
from app.core.security import hash_password
from app.modules.attendance.models import BreakType
from app.modules.complaints.models import ComplaintCategory
from app.modules.directory.models import User
from app.modules.leaves.models import LeaveType
from app.modules.rbac import service as rbac_service
from app.modules.rbac.models import Role
from app.modules.settings.models import BusinessSetting
from app.modules.settings.registry import SETTINGS_BY_KEY
from app.modules.settings.service import json_safe

BREAK_TYPES: list[dict[str, Any]] = [
    {
        "code": "LUNCH",
        "name": "Lunch",
        "is_paid": False,
        "max_minutes": 60,
        "requires_approval": False,
        "counts_toward_max_per_day": True,
        "sort_order": 1,
    },
    {
        "code": "TEA",
        "name": "Tea break",
        "is_paid": True,
        "max_minutes": 15,
        "requires_approval": False,
        "counts_toward_max_per_day": True,
        "sort_order": 2,
    },
]

LEAVE_TYPES: list[dict[str, Any]] = [
    {
        "code": "CASUAL",
        "name": "Casual leave",
        "is_paid": True,
        "requires_approval": True,
        "allow_half_day": True,
        "annual_entitlement_days": Decimal("12.00"),
        "accrual_mode": "MANUAL",
        "sort_order": 1,
    },
    {
        "code": "SICK",
        "name": "Sick leave",
        "is_paid": True,
        "requires_approval": True,
        "requires_attachment_after_days": 2,
        "allow_half_day": True,
        "annual_entitlement_days": Decimal("8.00"),
        "accrual_mode": "MANUAL",
        "sort_order": 2,
    },
    {
        "code": "UNPAID",
        "name": "Unpaid leave",
        "is_paid": False,
        "requires_approval": True,
        "allow_half_day": True,
        "annual_entitlement_days": Decimal("0.00"),
        "accrual_mode": "MANUAL",
        "sort_order": 3,
    },
]

COMPLAINT_CATEGORIES: list[dict[str, Any]] = [
    {"code": "WORKPLACE", "name": "Workplace", "default_priority": "NORMAL", "default_visibility": "EMPLOYEE_PRIVATE", "sort_order": 1},
    {"code": "EQUIPMENT", "name": "Equipment", "default_priority": "NORMAL", "default_visibility": "EMPLOYEE_PRIVATE", "sort_order": 2},
    {"code": "CUSTOMER", "name": "Customer", "default_priority": "HIGH", "default_visibility": "ADMIN_ONLY", "sort_order": 3},
    {"code": "OTHER", "name": "Other", "default_priority": "NORMAL", "default_visibility": "EMPLOYEE_PRIVATE", "sort_order": 4},
]


async def ensure_settings(session: AsyncSession) -> int:
    existing = set(
        (await session.execute(select(BusinessSetting.key))).scalars().all()
    )
    created = 0
    for definition in SETTINGS_BY_KEY.values():
        if definition.key in existing:
            continue
        session.add(
            BusinessSetting(
                key=definition.key,
                value=json_safe(definition.default),
                value_type=definition.value_type,
                description=definition.description,
                is_provisional=definition.provisional,
                version=1,
            )
        )
        created += 1
    await session.flush()
    return created


async def ensure_roles(session: AsyncSession) -> dict[str, Role]:
    await rbac_service.ensure_catalog(session)
    roles: dict[str, Role] = {}
    wanted = {
        "ADMIN": ("Administrator", "Full access to every capability", sorted(ALL_PERMISSION_CODES)),
        "EMPLOYEE": ("Employee", "Standard employee self-service", sorted(EMPLOYEE_PERMISSION_CODES)),
    }
    for code, (name, description, permissions) in wanted.items():
        role = (
            await session.execute(select(Role).where(Role.code == code))
        ).scalar_one_or_none()
        if role is None:
            role = Role(code=code, name=name, description=description, is_system=True, is_assignable=True)
            session.add(role)
            await session.flush()
        current = set(await rbac_service.role_permission_codes(session, role.id))
        if current != set(permissions):
            await rbac_service.set_role_permissions(
                session, role, permissions, actor_user_id=None
            )
        roles[code] = role
    return roles


async def ensure_break_types(session: AsyncSession) -> int:
    created = 0
    for item in BREAK_TYPES:
        existing = (
            await session.execute(select(BreakType).where(BreakType.code == item["code"]))
        ).scalar_one_or_none()
        if existing is None:
            session.add(BreakType(**item))
            created += 1
    await session.flush()
    return created


async def ensure_leave_types(session: AsyncSession) -> int:
    created = 0
    for item in LEAVE_TYPES:
        existing = (
            await session.execute(select(LeaveType).where(LeaveType.code == item["code"]))
        ).scalar_one_or_none()
        if existing is None:
            session.add(LeaveType(**item))
            created += 1
    await session.flush()
    return created


async def ensure_complaint_categories(session: AsyncSession) -> int:
    created = 0
    for item in COMPLAINT_CATEGORIES:
        existing = (
            await session.execute(
                select(ComplaintCategory).where(ComplaintCategory.code == item["code"])
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(ComplaintCategory(**item))
            created += 1
    await session.flush()
    return created


async def ensure_admin(
    session: AsyncSession,
    *,
    username: str = "admin",
    email: str | None = "admin@example.com",
    password: str = "ChangeMe123!",
) -> tuple[User, bool]:
    from datetime import date
    from app.modules.directory.models import Employee

    existing = (
        await session.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    created = False
    if existing is not None:
        user = existing
        await rbac_service.assign_roles(
            session, existing.id, ["ADMIN"], actor_user_id=None
        )
    else:
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            status="ACTIVE",
            must_change_password=False,
        )
        session.add(user)
        await session.flush()
        await rbac_service.assign_roles(
            session, user.id, ["ADMIN"], actor_user_id=None
        )
        created = True

    emp = (
        await session.execute(select(Employee).where(Employee.user_id == user.id))
    ).scalar_one_or_none()
    if emp is None:
        session.add(
            Employee(
                user_id=user.id,
                employee_code="ADMIN001",
                full_name="System Administrator",
                phone="9999999999",
                email=user.email or "admin@example.com",
                date_of_joining=date.today(),
                employment_status="ACTIVE",
                employment_type="FULL_TIME",
                department="Management",
                designation="Administrator",
            )
        )
        await session.flush()

    return user, created


async def seed_all(session: AsyncSession) -> dict[str, int]:
    created = {
        "settings": await ensure_settings(session),
        "break_types": await ensure_break_types(session),
        "leave_types": await ensure_leave_types(session),
        "complaint_categories": await ensure_complaint_categories(session),
    }
    await ensure_roles(session)
    return created