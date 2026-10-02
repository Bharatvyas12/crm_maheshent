"""Identity tables (docs/02_DATABASE.md sections 4.2 - 4.4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import INET, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, created_at_col, uuid_pk

REVOKE_REASONS = "('LOGOUT','PASSWORD_CHANGE','ADMIN_REVOKE','EMPLOYEE_DEACTIVATED','EXPIRED','SECURITY')"
FAILURE_REASONS = "('BAD_CREDENTIALS','LOCKED','DISABLED','SESSION_EXPIRED')"


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_col()
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            f"revoked_reason IS NULL OR revoked_reason IN {REVOKE_REASONS}",
            name="ck_sessions_revoked_reason",
        ),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
        Index("ix_sessions_active", "user_id", postgresql_where=text("revoked_at IS NULL")),
    )


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[int] = bigint_pk()
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    succeeded: Mapped[bool] = mapped_column(nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            f"failure_reason IS NULL OR failure_reason IN {FAILURE_REASONS}",
            name="ck_login_attempts_failure_reason",
        ),
        Index("ix_login_attempts_identifier_created_at", "identifier", text("created_at DESC")),
        Index("ix_login_attempts_user_created_at", "user_id", text("created_at DESC")),
    )


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text, nullable=False)