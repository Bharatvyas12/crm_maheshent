"""Request composition: session/auth resolution, dependencies, response helpers.

This is the composition root (docs/01_ARCHITECTURE.md section 7): it may import any
module's `service.py`; modules may not import each other's internals.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import RequestMeta
from app.core.authz import PASSWORD_CHANGE_ALLOWED_PATHS, AuthContext, current_auth
from app.core.config import get_config
from app.core.db import get_sessionmaker
from app.core.errors import (
    AuthenticationRequired,
    CsrfInvalid,
    PermissionDenied,
    ValidationError,
)
from app.core.security import constant_time_equals, sha256_hex
from app.modules.audit.service import audit
from app.modules.directory import service as directory_service
from app.modules.identity import service as identity_service
from app.modules.rbac import service as rbac_service
from app.modules.settings.service import SettingsService, SettingsView

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "x-csrf-token"
CSRF_COOKIE_NAME = "csrf_token"


@dataclass(slots=True)
class Ctx:
    session: AsyncSession
    settings: SettingsView
    meta: RequestMeta
    auth: AuthContext | None = None
    request: Request | None = None

    @property
    def actor(self) -> AuthContext:
        if self.auth is None:
            raise AuthenticationRequired("A valid session is required.")
        return self.auth

    @property
    def actor_user_id(self) -> uuid.UUID:
        return self.actor.user_id

    @property
    def employee_id(self) -> uuid.UUID:
        employee_id = self.actor.employee_id
        if employee_id is None:
            raise PermissionDenied("The acting user is not linked to an employee record.")
        return employee_id

    async def audit(
        self,
        *,
        category: str,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_type: str = "USER",
    ) -> None:
        audit(
            self.session,
            category=category,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before,
            after=after,
            reason=reason,
            meta=self.meta,
            actor_user_id=actor_user_id if actor_user_id is not None else (self.auth and self.auth.user_id),
            actor_type=actor_type,
        )


async def get_ctx(request: Request) -> AsyncIterator[Ctx]:
    """One transaction per request: commit on success, roll back on any error."""
    session = get_sessionmaker()()
    meta = RequestMeta(
        request_id=getattr(request.state, "request_id", None),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    try:
        settings = await SettingsService(session).load()
        auth: AuthContext | None = None
        raw_token = request.cookies.get(get_config().session_cookie_name)
        if raw_token:
            resolved = await identity_service.resolve_session(session, raw_token, settings)
            if resolved is not None:
                session_row, user = resolved
                if request.method in UNSAFE_METHODS:
                    _enforce_csrf(request, session_row)
                await identity_service.touch_session(session, session_row, settings)
                access = await rbac_service.effective_access(session, user.id)
                employee_id = await directory_service.employee_id_for_user(session, user.id)
                auth = AuthContext(
                    user_id=user.id,
                    username=user.username,
                    session_id=session_row.id,
                    permissions=access.permissions,
                    roles=access.roles,
                    employee_id=employee_id,
                    must_change_password=user.must_change_password,
                )
        request.state.auth = auth
        request.state.settings = settings
        ctx = Ctx(session=session, settings=settings, meta=meta, auth=auth, request=request)
        request.state.ctx = ctx
        yield ctx
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _enforce_csrf(request: Request, session_row: Any) -> None:
    """Double-submit CSRF check (docs/01_ARCHITECTURE.md section 11).

    The ``X-CSRF-Token`` header is mandatory on every unsafe method and must
    hash to the value bound to the session at login; the cookie alone is never
    sufficient (otherwise a cross-site form POST would replay it).
    """
    presented = request.headers.get(CSRF_HEADER)
    if not presented:
        raise CsrfInvalid("A CSRF token is required for this request.")
    if not constant_time_equals(sha256_hex(presented), session_row.csrf_token_hash):
        raise CsrfInvalid("The CSRF token is missing or invalid.")


AuthDep = Callable[..., Ctx]


def _check_password_gate(request: Request, auth: AuthContext) -> None:
    if auth.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise PermissionDenied(
            "A password change is required before using the application.",
            rule_code="PASSWORD_CHANGE_REQUIRED",
        )


def require(permission: str) -> AuthDep:
    """Dependency factory: enforce a catalog permission and return the request ctx.

    The dependency resolves :func:`get_ctx` so the request transaction, session
    resolution and permission loading always run before authorization checks.
    """

    def dependency(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        auth = ctx.auth
        if auth is None:
            raise AuthenticationRequired("A valid session is required.")
        if not auth.has(permission):
            raise PermissionDenied(f"Missing permission: {permission}")
        _check_password_gate(ctx.request, auth)
        return ctx

    return dependency


def require_any(*permissions: str) -> AuthDep:
    def dependency(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        auth = ctx.auth
        if auth is None:
            raise AuthenticationRequired("A valid session is required.")
        if not auth.has_any(*permissions):
            raise PermissionDenied("Missing required permission: " + " or ".join(permissions))
        _check_password_gate(ctx.request, auth)
        return ctx

    return dependency


def require_authenticated(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    auth = ctx.auth
    if auth is None:
        raise AuthenticationRequired("A valid session is required.")
    _check_password_gate(ctx.request, auth)
    return ctx


def parse_date(value: str | None, field_name: str) -> date | None:
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} must be an ISO date (YYYY-MM-DD).",
            errors=[{"field": field_name, "code": "INVALID_DATE", "message": str(exc)}],
        ) from exc


def parse_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(
            f"{field_name} must be an ISO 8601 timestamp.",
            errors=[{"field": field_name, "code": "INVALID_TIMESTAMP", "message": str(exc)}],
        ) from exc
    if parsed.tzinfo is None:
        raise ValidationError(f"{field_name} must include a timezone offset.")
    return parsed