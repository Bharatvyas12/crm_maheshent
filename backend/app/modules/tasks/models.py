"""Task tables (docs/02_DATABASE.md section 10)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bool_false, bool_true, created_at_col, uuid_pk, version_col

PRIORITIES = "('LOW','NORMAL','HIGH','URGENT')"
TASK_STATUS = "('ASSIGNED','IN_PROGRESS','SUBMITTED','COMPLETED','CANCELLED')"
ASSIGNMENT_STATUS = (
    "('ASSIGNED','STARTED','SUBMITTED','APPROVED','REJECTED','RESUBMISSION_REQUESTED','CANCELLED')"
)
REVIEW_DECISION = "('APPROVED','REJECTED','RESUBMISSION_REQUESTED')"
ATTACHMENT_TYPE = "('BRIEF','EVIDENCE','OTHER')"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ASSIGNED'"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requires_evidence: Mapped[bool] = bool_true()
    requires_attachment: Mapped[bool] = bool_false()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_tasks_title_length"),
        CheckConstraint(f"priority IN {PRIORITIES}", name="ck_tasks_priority"),
        CheckConstraint(f"status IN {TASK_STATUS}", name="ck_tasks_status"),
        Index("ix_tasks_status_due", "status", "due_at"),
        Index("ix_tasks_created_by", "created_by"),
        Index("ix_tasks_priority", "priority"),
    )


class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ASSIGNED'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    review_decision: Mapped[str | None] = mapped_column(Text)
    review_notes: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("task_id", "employee_id", name="uq_task_assignments_task_employee"),
        CheckConstraint(f"status IN {ASSIGNMENT_STATUS}", name="ck_task_assignments_status"),
        CheckConstraint(
            f"review_decision IS NULL OR review_decision IN {REVIEW_DECISION}",
            name="ck_task_assignments_review_decision",
        ),
        CheckConstraint(
            "(status IN ('APPROVED','REJECTED','RESUBMISSION_REQUESTED')) = (review_decision IS NOT NULL)",
            name="ck_task_assignments_reviewed_state",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_task_assignments_attempt_count"),
        Index("ix_task_assignments_employee_status", "employee_id", "status"),
        Index("ix_task_assignments_status_due", "status", "due_at"),
    )


class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id: Mapped[uuid.UUID] = uuid_pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_assignments.id"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    decision: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        UniqueConstraint("assignment_id", "attempt_no", name="uq_task_submissions_assignment_attempt"),
        CheckConstraint("attempt_no >= 1", name="ck_task_submissions_attempt_no"),
        CheckConstraint(
            f"decision IS NULL OR decision IN {REVIEW_DECISION}",
            name="ck_task_submissions_decision",
        ),
        CheckConstraint(
            "decision IS NULL OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_task_submissions_decided",
        ),
        Index("ix_task_submissions_assignment", "assignment_id", text("attempt_no DESC")),
    )


class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_assignments.id")
    )
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = bool_false()
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="ck_task_comments_body"),
        Index("ix_task_comments_task_created", "task_id", "created_at"),
    )


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    task_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_assignments.id")
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_submissions.id")
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), nullable=False, unique=True
    )
    attachment_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"attachment_type IN {ATTACHMENT_TYPE}", name="ck_task_attachments_type"),
        Index("ix_task_attachments_task", "task_id"),
        Index("ix_task_attachments_submission", "submission_id"),
    )