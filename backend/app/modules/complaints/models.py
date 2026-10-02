"""Complaint tables (docs/02_DATABASE.md section 14)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, bool_false, bool_true, created_at_col, uuid_pk, version_col

PRIORITIES = "('LOW','NORMAL','HIGH','URGENT')"
COMPLAINT_STATUS = "('OPEN','IN_REVIEW','ACTION_REQUIRED','RESOLVED','CLOSED','REJECTED')"
VISIBILITY = "('EMPLOYEE_PRIVATE','ADMIN_ONLY','INTERNAL_TEAM')"


class ComplaintCategory(Base):
    __tablename__ = "complaint_categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    default_priority: Mapped[str | None] = mapped_column(Text)
    default_visibility: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = bool_true()
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(
            f"default_priority IS NULL OR default_priority IN {PRIORITIES}",
            name="ck_complaint_categories_priority",
        ),
        CheckConstraint(
            f"default_visibility IS NULL OR default_visibility IN {VISIBILITY}",
            name="ck_complaint_categories_visibility",
        ),
    )


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = uuid_pk()
    complaint_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("complaint_categories.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'OPEN'"))
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    raised_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    subject_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(f"priority IN {PRIORITIES}", name="ck_complaints_priority"),
        CheckConstraint(f"status IN {COMPLAINT_STATUS}", name="ck_complaints_status"),
        CheckConstraint(f"visibility IN {VISIBILITY}", name="ck_complaints_visibility"),
        CheckConstraint("status <> 'RESOLVED' OR resolved_at IS NOT NULL", name="ck_complaints_resolved"),
        CheckConstraint("status <> 'CLOSED' OR closed_at IS NOT NULL", name="ck_complaints_closed"),
        CheckConstraint("status <> 'REJECTED' OR rejection_reason IS NOT NULL", name="ck_complaints_rejected"),
        Index("ix_complaints_status_priority", "status", "priority"),
        Index("ix_complaints_raised_by", "raised_by", text("created_at DESC")),
        Index("ix_complaints_subject", "subject_employee_id"),
        Index("ix_complaints_assigned", "assigned_to", "status"),
    )


class ComplaintComment(Base):
    __tablename__ = "complaint_comments"

    id: Mapped[uuid.UUID] = uuid_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("complaints.id"), nullable=False
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = bool_false()
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="ck_complaint_comments_body"),
        Index("ix_complaint_comments_complaint_created", "complaint_id", "created_at"),
    )


class ComplaintAttachment(Base):
    __tablename__ = "complaint_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("complaints.id"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), nullable=False, unique=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    note: Mapped[str | None] = mapped_column(Text)


class ComplaintStatusHistory(Base):
    __tablename__ = "complaint_status_history"

    id: Mapped[int] = bigint_pk()
    complaint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("complaints.id"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    is_internal_note: Mapped[bool] = bool_false()
    meta: Mapped[Any | None] = mapped_column("metadata", JSONB)
    changed_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        Index("ix_complaint_status_history_complaint_changed", "complaint_id", "changed_at"),
    )