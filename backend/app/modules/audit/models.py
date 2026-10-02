"""Audit table (docs/02_DATABASE.md section 16.1). Append-only."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, created_at_col

AUDIT_CATEGORIES = (
    "('AUTH','SECURITY','PERMISSION','EMPLOYEE','SETTINGS','ATTENDANCE','TASK','ORDER',"
    "'LEAVE','FINANCIAL','COMPLAINT','FILE')"
)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = bigint_pk()
    category: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USER'"))
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    before: Mapped[Any | None] = mapped_column(JSONB)
    after: Mapped[Any | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"category IN {AUDIT_CATEGORIES}", name="ck_audit_logs_category"),
        CheckConstraint("actor_type IN ('USER','SYSTEM','ANONYMOUS')", name="ck_audit_logs_actor_type"),
        Index("ix_audit_logs_entity", "entity_type", "entity_id", text("created_at DESC")),
        Index("ix_audit_logs_actor", "actor_user_id", text("created_at DESC")),
        Index("ix_audit_logs_category_created", "category", text("created_at DESC")),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", text("created_at DESC")),
    )