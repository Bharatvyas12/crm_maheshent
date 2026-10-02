"""Authentication and session endpoints (docs/03_API_CONTRACT.md section 2)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.context import Ctx, get_ctx, require, require_authenticated
from app.api.payloads import build_session_payload, user_payload
from app.core.config import get_config
from app.core.errors import NotFound
from app.core.timeutil import utcnow
from app.modules.audit.service import audit
from app.modules.directory import service as directory_service
from app.modules.identity import service as identity_service

router = APIRouter(tags=["auth"])

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=512)


class ResetPasswordRequest(BaseModel):
    user_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class ResetPasswordConfirmRequest(BaseModel):
    reset_token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=1, max_length=512)


def _set_session_cookies(response: Response, ctx: Ctx, bundle: identity_service.SessionBundle) -> None:
    config = get_config()
    max_age = ctx.settings.int_("security.session_timeout_minutes") * 60
    response.set_cookie(
        config.session_cookie_name,
        bundle.raw_token,
        max_age=max_age,
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        domain=config.cookie_domain,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        bundle.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=config.cookie_secure,
        samesite="lax",
        domain=config.cookie_domain,
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    config = get_config()
    response.delete_cookie(config.session_cookie_name, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/auth/login")
async def login(
    payload: LoginRequest, request: Request, response: Response, ctx: Ctx = Depends(get_ctx)
) -> dict:
    user = await identity_service.authenticate(
        ctx.session,
        identifier=payload.username,
        password=payload.password,
        settings=ctx.settings,
        ip=ctx.meta.ip,
        user_agent=ctx.meta.user_agent,
    )
    bundle = await identity_service.create_session(
        ctx.session, user, ctx.settings, ip=ctx.meta.ip, user_agent=ctx.meta.user_agent
    )
    employee_id = await directory_service.employee_id_for_user(ctx.session, user.id)
    audit(
        ctx.session,
        category="AUTH",
        action="auth.login.succeeded",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        meta=ctx.meta,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "identity.session.created.v1",
        aggregate_type="session",
        aggregate_id=bundle.session.id,
        actor_user_id=user.id,
        payload={"user_id": str(user.id)},
    )
    _set_session_cookies(response, ctx, bundle)
    return await build_session_payload(
        ctx.session, user=user, settings=ctx.settings, employee_id=employee_id
    )


@router.post("/auth/logout", status_code=204)
async def logout(response: Response, ctx: Ctx = Depends(require_authenticated)) -> Response:
    if ctx.auth is not None:
        await identity_service.revoke_session(
            ctx.session, ctx.auth.session_id, user_id=ctx.auth.user_id, reason="LOGOUT"
        )
        await ctx.audit(
            category="AUTH", action="auth.logout", entity_type="session", entity_id=ctx.auth.session_id
        )
    _clear_session_cookies(response)
    response.status_code = 204
    return response


@router.get("/auth/me")
async def me(ctx: Ctx = Depends(require_authenticated)) -> dict:
    auth = ctx.actor
    user = await directory_service.get_user(ctx.session, auth.user_id)
    return await build_session_payload(
        ctx.session, user=user, settings=ctx.settings, employee_id=auth.employee_id
    )


@router.post("/auth/change-password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest, ctx: Ctx = Depends(require_authenticated)
) -> Response:
    auth = ctx.actor
    user = await directory_service.get_user(ctx.session, auth.user_id)
    await identity_service.change_password(
        ctx.session,
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        settings=ctx.settings,
        current_session_id=auth.session_id,
    )
    await ctx.audit(
        category="AUTH", action="auth.password.changed", entity_type="user", entity_id=user.id
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "identity.session.created.v1",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_user_id=user.id,
        payload={"action": "password_changed"},
    )
    return Response(status_code=204)


@router.post("/auth/reset-password", status_code=201)
async def reset_password(
    payload: ResetPasswordRequest, ctx: Ctx = Depends(require("employee.manage.credentials"))
) -> dict:
    target = await directory_service.get_user(ctx.session, payload.user_id)
    token, row = await identity_service.create_password_reset(
        ctx.session,
        target=target,
        actor_user_id=ctx.actor_user_id,
        reason=payload.reason,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="SECURITY",
        action="auth.password.reset_issued",
        entity_type="user",
        entity_id=target.id,
        reason=payload.reason,
    )
    return {"user_id": target.id, "reset_token": token, "expires_at": row.expires_at}


@router.post("/auth/reset-password/confirm", status_code=204)
async def reset_password_confirm(
    payload: ResetPasswordConfirmRequest, ctx: Ctx = Depends(get_ctx)
) -> Response:
    """Consume a reset token issued by an administrator (additive, see change log)."""
    user = await identity_service.consume_password_reset(
        ctx.session, payload.reset_token, payload.new_password, ctx.settings
    )
    audit(
        ctx.session,
        category="SECURITY",
        action="auth.password.reset_consumed",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=user.id,
        meta=ctx.meta,
    )
    return Response(status_code=204)


@router.get("/auth/sessions")
async def list_sessions(ctx: Ctx = Depends(require_authenticated)) -> dict:
    auth = ctx.actor
    rows = await identity_service.list_sessions(ctx.session, auth.user_id)
    items = [
        {
            "id": row.id,
            "created_at": row.created_at,
            "last_seen_at": row.last_seen_at,
            "expires_at": row.expires_at,
            "idle_expires_at": row.idle_expires_at,
            "ip": str(row.ip) if row.ip else None,
            "user_agent": row.user_agent,
            "is_current": row.id == auth.session_id,
        }
        for row in rows
    ]
    return {"items": items}


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: uuid.UUID, ctx: Ctx = Depends(require_authenticated)
) -> Response:
    auth = ctx.actor
    if not auth.has("auth.session.revoke.self"):
        from app.core.errors import PermissionDenied

        raise PermissionDenied("Missing permission: auth.session.revoke.self")
    try:
        await identity_service.revoke_session(
            ctx.session, session_id, user_id=auth.user_id, reason="USER_REVOKED"
        )
    except NotFound as exc:
        raise NotFound("Session not found.") from exc
    await ctx.audit(
        category="AUTH", action="auth.session.revoked", entity_type="session", entity_id=session_id
    )
    return Response(status_code=204)