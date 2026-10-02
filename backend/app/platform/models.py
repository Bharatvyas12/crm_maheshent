"""Platform tables (docs/02_DATABASE.md section 17)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, created_at_col, uuid_pk


class DomainEvent(Base):
    __tablename__ = "domain_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = created_at_col()
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_domain_events_attempts"),
        Index(
            "ix_domain_events_pending",
            "next_attempt_at",
            "occurred_at",
            postgresql_where=text("dispatched_at IS NULL"),
        ),
        Index("ix_domain_events_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_domain_events_type_occurred", "event_type", text("occurred_at DESC")),
    )


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'IN_PROGRESS'"))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("state IN ('IN_PROGRESS','COMPLETED','FAILED')", name="ck_idempotency_keys_state"),
        CheckConstraint("char_length(key) BETWEEN 1 AND 128", name="ck_idempotency_keys_key_length"),
        UniqueConstraint("user_id", "endpoint", "key", name="uq_idempotency_keys_scope"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = bigint_pk()
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = created_at_col()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    host: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED','SKIPPED_LOCKED')", name="ck_job_runs_status"
        ),
        CheckConstraint("items_processed >= 0", name="ck_job_runs_items"),
        Index("ix_job_runs_name_started", "job_name", text("started_at DESC")),
    )