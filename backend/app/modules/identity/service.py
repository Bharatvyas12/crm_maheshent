"""Identity service: authentication, sessions, password lifecycle.

Session tokens are opaque 256-bit values returned only in cookies; the database
stores only their SHA-256 hash (docs/01_ARCHITECTURE.md section 11).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AccountDisabled,
    AccountLocked,
    InvalidCredentials,
    NotFound,
    RateLimited,
    RuleViolation,
    ValidationError,
)
from app.core.security import (
    hash_password,
    needs_rehash,
    new_opaque_token,
    sha256_hex,
    verify_password,
)
from app.core.timeutil import utcnow
from app.modules.directory.models import User
from app.modules.identity.models import LoginAttempt, PasswordResetToken, Session
from app.modules.rbac import service as rbac_service
from app.modules.settings.service import SettingsView

USER_STATUS_ACTIVE = "ACTIVE"
COMPLEXITY_CLASSES = ("upper", "lower", "digit", "symbol")


@dataclass(slots=True)
class SessionBundle:
    session: Session
    raw_token: str
    csrf_token: str


def validate_password_policy(settings: SettingsView, password: str) -> None:
    min_length = settings.int_("security.password_min_length")
    errors = []
    if len(password) < min_length:
        errors.append(
            {
                "field": "new_password",
                "code": "TOO_SHORT",
                "message": f"Password must be at least {min_length} characters.",
            }
        )
    if settings.bool_("security.password_require_complexity"):
        checks = {
            "upper": any(c.isupper() for c in password),
            "lower": any(c.islower() for c in password),
            "digit": any(c.isdigit() for c in password),
            "symbol": any(not c.isalnum() for c in password),
        }
        missing = [name for name in COMPLEXITY_CLASSES if not checks[name]]
        if missing:
            errors.append(
                {
                    "field": "new_password",
                    "code": "TOO_SIMPLE",
                    "message": "Password must include: " + ", ".join(missing) + ".",
                }
            )
    if errors:
        raise ValidationError("Password does not meet the configured policy.", errors=errors)


async def _recent_attempt_count(
    session: AsyncSession, identifier: str, window_minutes: int
) -> int:
    since = utcnow() - timedelta(minutes=window_minutes)
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(LoginAttempt)
                .where(LoginAttempt.identifier == identifier, LoginAttempt.created_at >= since)
            )
        ).scalar_one()
    )


async def _record_attempt(
    session: AsyncSession,
    *,
    identifier: str,
    user_id: uuid.UUID | None,
    succeeded: bool,
    failure_reason: str | None,
    ip: str | None,
    user_agent: str | None,
) -> None:
    session.add(
        LoginAttempt(
            identifier=identifier[:255],
            user_id=user_id,
            succeeded=succeeded,
            failure_reason=failure_reason,
            ip=ip,
            user_agent=(user_agent or None) and user_agent[:400],
        )
    )
    await session.flush()


async def find_user_by_identifier(session: AsyncSession, identifier: str) -> User | None:
    value = identifier.strip()
    stmt = select(User).where(or_(User.username == value, User.email == value))
    return (await session.execute(stmt)).scalar_one_or_none()


async def authenticate(
    session: AsyncSession,
    *,
    identifier: str,
    password: str,
    settings: SettingsView,
    ip: str | None,
    user_agent: str | None,
) -> User:
    identifier = (identifier or "").strip()
    if not identifier or not password:
        raise ValidationError(
            "Username and password are required.",
            errors=[{"field": "username", "code": "REQUIRED", "message": "Required"}],
        )
    throttle = settings.int_("security.rate_limit.login_per_minute")
    if await _recent_attempt_count(session, identifier, 1) >= throttle:
        raise RateLimited("Too many login attempts. Try again shortly.", rule_code="LOGIN_THROTTLED")

    user = await find_user_by_identifier(session, identifier)
    if user is None:
        await _record_attempt(
            session,
            identifier=identifier,
            user_id=None,
            succeeded=False,
            failure_reason="BAD_CREDENTIALS",
            ip=ip,
            user_agent=user_agent,
        )
        raise InvalidCredentials("Invalid username or password.")

    if user.status != USER_STATUS_ACTIVE:
        await _record_attempt(
            session,
            identifier=identifier,
            user_id=user.id,
            succeeded=False,
            failure_reason="DISABLED",
            ip=ip,
            user_agent=user_agent,
        )
        raise AccountDisabled("This account is disabled.")

    now = utcnow()
    if user.locked_until is not None and user.locked_until > now:
        await _record_attempt(
            session,
            identifier=identifier,
            user_id=user.id,
            succeeded=False,
            failure_reason="LOCKED",
            ip=ip,
            user_agent=user_agent,
        )
        raise AccountLocked("This account is temporarily locked.", extra={"locked_until": user.locked_until.isoformat()})

    if not verify_password(user.password_hash, password):
        window = settings.int_("security.lockout_window_minutes")
        max_failures = settings.int_("security.max_failed_logins")
        failures = await _recent_attempt_count(session, identifier, window)
        user.failed_login_count = int(user.failed_login_count or 0) + 1
        if failures + 1 >= max_failures:
            user.locked_until = now + timedelta(minutes=settings.int_("security.lockout_minutes"))
        await _record_attempt(
            session,
            identifier=identifier,
            user_id=user.id,
            succeeded=False,
            failure_reason="BAD_CREDENTIALS",
            ip=ip,
            user_agent=user_agent,
        )
        await session.flush()
        raise InvalidCredentials("Invalid username or password.")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await _record_attempt(
        session,
        identifier=identifier,
        user_id=user.id,
        succeeded=True,
        failure_reason=None,
        ip=ip,
        user_agent=user_agent,
    )
    await session.flush()
    return user

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


async def create_session(
    session: AsyncSession,
    user: User,
    settings: SettingsView,
    *,
    ip: str | None,
    user_agent: str | None,
) -> SessionBundle:
    now = utcnow()
    raw_token = new_opaque_token()
    csrf_token = new_opaque_token()
    absolute = now + timedelta(minutes=settings.int_("security.session_timeout_minutes"))
    idle = now + timedelta(minutes=settings.int_("security.session_idle_timeout_minutes"))
    row = Session(
        user_id=user.id,
        token_hash=sha256_hex(raw_token),
        csrf_token_hash=sha256_hex(csrf_token),
        created_at=now,
        last_seen_at=now,
        expires_at=absolute,
        idle_expires_at=min(idle, absolute),
        ip=ip,
        user_agent=(user_agent or None) and user_agent[:400],
    )
    session.add(row)
    await session.flush()
    return SessionBundle(session=row, raw_token=raw_token, csrf_token=csrf_token)


async def resolve_session(
    session: AsyncSession, raw_token: str, settings: SettingsView
) -> tuple[Session, User] | None:
    if not raw_token:
        return None
    row = (
        await session.execute(
            select(Session).where(Session.token_hash == sha256_hex(raw_token))
        )
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    now = utcnow()
    if row.expires_at <= now or row.idle_expires_at <= now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.status != USER_STATUS_ACTIVE:
        return None
    return row, user


async def touch_session(session: AsyncSession, row: Session, settings: SettingsView) -> None:
    now = utcnow()
    idle = now + timedelta(minutes=settings.int_("security.session_idle_timeout_minutes"))
    row.last_seen_at = now
    row.idle_expires_at = min(idle, row.expires_at)
    await session.flush()


async def revoke_session(
    session: AsyncSession, session_id: uuid.UUID, *, user_id: uuid.UUID, reason: str
) -> None:
    row = await session.get(Session, session_id)
    if row is None or row.user_id != user_id:
        raise NotFound("Session not found.")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        row.revoked_reason = reason
    await session.flush()


async def revoke_all_sessions(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    reason: str,
    except_session_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow(), revoked_reason=reason)
    )
    if except_session_id is not None:
        stmt = stmt.where(Session.id != except_session_id)
    result = await session.execute(stmt)
    await session.flush()
    return int(result.rowcount or 0)


async def list_sessions(session: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    now = utcnow()
    return list(
        (
            await session.execute(
                select(Session)
                .where(
                    Session.user_id == user_id,
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                    Session.idle_expires_at > now,
                )
                .order_by(Session.created_at.desc())
            )
        ).scalars().all()
    )


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_password: str,
    new_password: str,
    settings: SettingsView,
    current_session_id: uuid.UUID,
) -> None:
    if not verify_password(user.password_hash, current_password):
        raise InvalidCredentials("Current password is incorrect.")
    validate_password_policy(settings, new_password)
    if verify_password(user.password_hash, new_password):
        raise RuleViolation(
            "The new password must differ from the current password.",
            rule_code="PASSWORD_REUSE",
        )
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    await session.flush()
    await revoke_all_sessions(
        session, user.id, reason="PASSWORD_CHANGED", except_session_id=current_session_id
    )


async def create_password_reset(
    session: AsyncSession,
    *,
    target: User,
    actor_user_id: uuid.UUID,
    reason: str,
    settings: SettingsView,
) -> tuple[str, PasswordResetToken]:
    raw = new_opaque_token()
    row = PasswordResetToken(
        user_id=target.id,
        token_hash=sha256_hex(raw),
        created_by=actor_user_id,
        expires_at=utcnow() + timedelta(minutes=settings.int_("security.password_reset_ttl_minutes")),
        reason=reason,
    )
    session.add(row)
    target.must_change_password = True
    await session.flush()
    await revoke_all_sessions(session, target.id, reason="PASSWORD_RESET_ISSUED")
    return raw, row


async def consume_password_reset(
    session: AsyncSession, raw_token: str, new_password: str, settings: SettingsView
) -> User:
    row = (
        await session.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == sha256_hex(raw_token))
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise InvalidCredentials("This password reset token is invalid or has expired.")
    user = await session.get(User, row.user_id)
    if user is None:
        raise NotFound("User not found.")
    validate_password_policy(settings, new_password)
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    row.used_at = utcnow()
    await session.flush()
    await revoke_all_sessions(session, user.id, reason="PASSWORD_RESET_USED")
    return user