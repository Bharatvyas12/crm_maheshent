"""RBAC service: effective permissions and role administration."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import ALL_PERMISSION_CODES, PERMISSION_CATALOG
from app.core.errors import DuplicateConflict, NotFound, RuleViolation, ValidationError
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole

ADMIN_ROLE_CODE = "ADMIN"
EMPLOYEE_ROLE_CODE = "EMPLOYEE"


@dataclass(slots=True)
class EffectiveAccess:
    roles: tuple[str, ...]
    permissions: frozenset[str]


async def effective_access(session: AsyncSession, user_id: uuid.UUID) -> EffectiveAccess:
    role_rows = (
        await session.execute(
            select(Role.code, Role.id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.code)
        )
    ).all()
    roles = tuple(row[0] for row in role_rows)
    role_ids = [row[1] for row in role_rows]
    if not role_ids:
        return EffectiveAccess(roles=roles, permissions=frozenset())
    if ADMIN_ROLE_CODE in roles:
        return EffectiveAccess(roles=roles, permissions=ALL_PERMISSION_CODES)
    codes = (
        await session.execute(
            select(func.distinct(Permission.code))
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(role_ids))
        )
    ).scalars().all()
    return EffectiveAccess(roles=roles, permissions=frozenset(codes))


async def ensure_catalog(session: AsyncSession) -> int:
    """Insert any permission rows missing from the catalog (idempotent)."""
    existing = set((await session.execute(select(Permission.code))).scalars().all())
    added = 0
    for code, module, is_sensitive, description in PERMISSION_CATALOG:
        if code in existing:
            continue
        session.add(
            Permission(code=code, module=module, description=description, is_sensitive=is_sensitive)
        )
        added += 1
    await session.flush()
    return added


async def get_role_by_code(session: AsyncSession, code: str) -> Role:
    role = (
        await session.execute(select(Role).where(Role.code == code))
    ).scalar_one_or_none()
    if role is None:
        raise NotFound(f"Role {code} not found.")
    return role


async def get_role(session: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await session.get(Role, role_id)
    if role is None:
        raise NotFound("Role not found.")
    return role


async def role_permission_codes(session: AsyncSession, role_id: uuid.UUID) -> list[str]:
    rows = (
        await session.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.code)
        )
    ).scalars().all()
    return list(rows)


async def set_role_permissions(
    session: AsyncSession,
    role: Role,
    codes: list[str],
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    unknown = sorted(set(codes) - ALL_PERMISSION_CODES)
    if unknown:
        raise ValidationError(
            "Unknown permission codes: " + ", ".join(unknown),
            errors=[{"field": "permission_codes", "code": "UNKNOWN", "message": code} for code in unknown],
        )
    permission_ids = dict(
        (await session.execute(select(Permission.code, Permission.id))).all()
    )
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    from app.core.timeutil import utcnow

    now = utcnow()
    for code in sorted(set(codes)):
        session.add(
            RolePermission(
                role_id=role.id,
                permission_id=permission_ids[code],
                granted_at=now,
                granted_by=actor_user_id,
            )
        )
    await session.flush()


async def create_role(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    description: str | None,
    permission_codes: list[str] | None,
    actor_user_id: uuid.UUID | None,
) -> Role:
    existing = (await session.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
    if existing is not None:
        raise DuplicateConflict(f"Role code {code} already exists.")
    role = Role(
        code=code,
        name=name,
        description=description,
        is_system=False,
        is_assignable=True,
    )
    session.add(role)
    await session.flush()
    if permission_codes:
        await set_role_permissions(session, role, permission_codes, actor_user_id=actor_user_id)
    return role


async def delete_role(session: AsyncSession, role: Role) -> None:
    if role.is_system:
        raise RuleViolation("System roles cannot be deleted.", rule_code="SYSTEM_ROLE_PROTECTED")
    assigned = (
        await session.execute(
            select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id)
        )
    ).scalar_one()
    if assigned:
        raise RuleViolation(
            "Role is assigned to users and cannot be deleted.", rule_code="ROLE_IN_USE"
        )
    await session.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    await session.delete(role)
    await session.flush()


async def assign_roles(
    session: AsyncSession,
    user_id: uuid.UUID,
    role_codes: list[str],
    *,
    actor_user_id: uuid.UUID | None,
) -> list[str]:
    roles = (
        await session.execute(select(Role).where(Role.code.in_(role_codes)))
    ).scalars().all()
    found = {role.code for role in roles}
    missing = sorted(set(role_codes) - found)
    if missing:
        raise NotFound("Unknown role codes: " + ", ".join(missing))
    from app.core.timeutil import utcnow

    now = utcnow()
    await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for role in roles:
        session.add(
            UserRole(user_id=user_id, role_id=role.id, assigned_at=now, assigned_by=actor_user_id)
        )
    await session.flush()
    return sorted(found)