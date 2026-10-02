"""Response payload composition shared by the auth endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.directory import service as directory_service
from app.modules.rbac import service as rbac_service
from app.modules.settings.service import SettingsView


def user_payload(user: Any) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "status": user.status,
        "last_login_at": user.last_login_at,
        "must_change_password": user.must_change_password,
        "created_at": user.created_at,
    }


async def build_session_payload(
    session: AsyncSession,
    *,
    user: Any,
    settings: SettingsView,
    employee_id: uuid.UUID | None,
) -> dict[str, Any]:
    access = await rbac_service.effective_access(session, user.id)
    employee = None
    if employee_id is not None:
        employee = await directory_service.get_employee(session, employee_id)
    return {
        "user": user_payload(user),
        "employee": directory_service.serialize_employee(
            employee, include_sensitive=False, employee_id=employee_id
        )
        if employee
        else None,
        "roles": list(access.roles),
        "permissions": sorted(access.permissions),
        "settings": settings.employee_payload(),
    }