"""Tasks service: assignment, submission and review lifecycle."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound, RuleViolation, ValidationError
from app.core.timeutil import utcnow
from app.modules.directory.models import Employee
from app.modules.settings.service import SettingsView
from app.modules.tasks.models import (
    Task,
    TaskAssignment,
    TaskAttachment,
    TaskComment,
    TaskSubmission,
)

TERMINAL_ASSIGNMENT = frozenset({"APPROVED", "REJECTED", "CANCELLED"})
OPEN_ASSIGNMENT = frozenset({"ASSIGNED", "STARTED", "SUBMITTED", "RESUBMISSION_REQUESTED"})


def allowed_transitions(assignment: TaskAssignment, *, is_assignee: bool, can_review: bool) -> list[str]:
    status = assignment.status
    result: list[str] = []
    if status == "ASSIGNED" and is_assignee:
        result.append("STARTED")
    if status in {"ASSIGNED", "STARTED", "RESUBMISSION_REQUESTED"} and is_assignee:
        result.append("SUBMITTED")
    if status == "STARTED" and is_assignee:
        result.append("COMPLETED")
    if status == "SUBMITTED" and can_review:
        result.extend(["APPROVED", "REJECTED", "RESUBMISSION_REQUESTED"])
    return result


def serialize_assignment(
    assignment: TaskAssignment,
    task: Task | None = None,
    *,
    transitions: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": assignment.id,
        "task_id": assignment.task_id,
        "employee_id": assignment.employee_id,
        "assigned_by": assignment.assigned_by,
        "assigned_at": assignment.assigned_at,
        "status": assignment.status,
        "started_at": assignment.started_at,
        "completed_at": assignment.completed_at,
        "submitted_at": assignment.submitted_at,
        "reviewed_at": assignment.reviewed_at,
        "reviewer_id": assignment.reviewer_id,
        "review_decision": assignment.review_decision,
        "review_notes": assignment.review_notes,
        "attempt_count": assignment.attempt_count,
        "due_at": assignment.due_at,
        "version": assignment.version,
    }
    if task is not None:
        payload["task"] = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "status": task.status,
            "due_at": task.due_at,
            "requires_evidence": task.requires_evidence,
            "requires_attachment": task.requires_attachment,
        }
    if transitions is not None:
        payload["allowed_transitions"] = transitions
    return payload


def serialize_task(task: Task, transitions: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "created_by": task.created_by,
        "due_at": task.due_at,
        "requires_evidence": task.requires_evidence,
        "requires_attachment": task.requires_attachment,
        "completed_at": task.completed_at,
        "cancelled_at": task.cancelled_at,
        "cancel_reason": task.cancel_reason,
        "version": task.version,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }
    if transitions is not None:
        payload["allowed_transitions"] = transitions
    return payload


def serialize_submission(row: TaskSubmission, *, evidence: list[dict] | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "assignment_id": row.assignment_id,
        "attempt_no": row.attempt_no,
        "description": row.description,
        "submitted_by": row.submitted_by,
        "submitted_at": row.submitted_at,
        "decision": row.decision,
        "decided_by": row.decided_by,
        "decided_at": row.decided_at,
        "decision_notes": row.decision_notes,
    }
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def serialize_comment(row: TaskComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "assignment_id": row.assignment_id,
        "author_user_id": row.author_user_id,
        "body": row.body,
        "is_internal": row.is_internal,
        "created_at": row.created_at,
    }


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    row = await session.get(Task, task_id)
    if row is None:
        raise NotFound("Task not found.")
    return row


async def get_assignment(session: AsyncSession, assignment_id: uuid.UUID) -> TaskAssignment:
    row = await session.get(TaskAssignment, assignment_id)
    if row is None:
        raise NotFound("Task assignment not found.")
    return row


async def get_submission(session: AsyncSession, submission_id: uuid.UUID) -> TaskSubmission:
    row = await session.get(TaskSubmission, submission_id)
    if row is None:
        raise NotFound("Task submission not found.")
    return row


async def count_open_assignments(session: AsyncSession, employee_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(TaskAssignment)
                .where(
                    TaskAssignment.employee_id == employee_id,
                    TaskAssignment.status.in_(list(OPEN_ASSIGNMENT)),
                )
            )
        ).scalar_one()
    )


async def create_task(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    title: str,
    description: str | None,
    priority: str,
    due_at: datetime | None,
    requires_evidence: bool | None,
    requires_attachment: bool | None,
    employee_ids: list[uuid.UUID],
    settings: SettingsView,
) -> tuple[Task, list[TaskAssignment]]:
    if len(employee_ids) > 1 and not settings.bool_("tasks.allow_multiple_assignees"):
        raise RuleViolation(
            "Only one assignee is allowed per task.", rule_code="MULTIPLE_ASSIGNEES_DISABLED"
        )
    task = Task(
        title=title,
        description=description,
        priority=priority,
        status="ASSIGNED",
        created_by=actor_user_id,
        due_at=due_at,
        requires_evidence=bool(requires_evidence) if requires_evidence is not None else True,
        requires_attachment=bool(requires_attachment) if requires_attachment is not None else settings.str_("tasks.attachment_mode") == "REQUIRED",
    )
    session.add(task)
    await session.flush()
    assignments = await assign_employees(
        session,
        task=task,
        employee_ids=employee_ids,
        actor_user_id=actor_user_id,
        due_at=due_at,
    )
    return task, assignments


async def assign_employees(
    session: AsyncSession,
    *,
    task: Task,
    employee_ids: list[uuid.UUID],
    actor_user_id: uuid.UUID,
    due_at: datetime | None = None,
) -> list[TaskAssignment]:
    created: list[TaskAssignment] = []
    for employee_id in dict.fromkeys(employee_ids):
        employee = await session.get(Employee, employee_id)
        if employee is None or employee.employment_status != "ACTIVE":
            raise NotFound(f"Employee {employee_id} is not an active employee.")
        existing = (
            await session.execute(
                select(TaskAssignment.id).where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        row = TaskAssignment(
            task_id=task.id,
            employee_id=employee_id,
            assigned_by=actor_user_id,
            status="ASSIGNED",
            attempt_count=0,
            due_at=due_at or task.due_at,
        )
        session.add(row)
        created.append(row)
    await session.flush()
    return created


async def start_assignment(
    session: AsyncSession, assignment: TaskAssignment, *, actor_user_id: uuid.UUID
) -> TaskAssignment:
    if assignment.status not in {"ASSIGNED", "RESUBMISSION_REQUESTED"}:
        raise Conflict(f"An assignment in status {assignment.status} cannot be started.")
    assignment.status = "STARTED"
    assignment.started_at = assignment.started_at or utcnow()
    task = await get_task(session, assignment.task_id)
    if task.status == "ASSIGNED":
        task.status = "IN_PROGRESS"
    await session.flush()
    return assignment


async def complete_assignment(
    session: AsyncSession, assignment: TaskAssignment
) -> TaskAssignment:
    if assignment.status != "STARTED":
        raise Conflict("Only a started assignment can be completed.")
    assignment.completed_at = utcnow()
    await session.flush()
    return assignment


async def submit_assignment(
    session: AsyncSession,
    *,
    assignment: TaskAssignment,
    actor_user_id: uuid.UUID,
    description: str | None,
    evidence_file_ids: list[uuid.UUID],
    settings: SettingsView,
) -> TaskSubmission:
    if assignment.status not in {"ASSIGNED", "STARTED", "RESUBMISSION_REQUESTED"}:
        raise Conflict(f"An assignment in status {assignment.status} cannot be submitted.")
    task = await get_task(session, assignment.task_id)
    if settings.bool_("tasks.require_evidence_on_submit") and not (description or evidence_file_ids):
        raise RuleViolation(
            "Evidence is required when submitting this task.", rule_code="EVIDENCE_REQUIRED"
        )
    if task.requires_attachment and not evidence_file_ids:
        raise RuleViolation(
            "An attachment is required for this task.", rule_code="ATTACHMENT_REQUIRED"
        )
    max_attachments = settings.int_("tasks.max_attachments_per_submission")
    if len(evidence_file_ids) > max_attachments:
        raise RuleViolation(
            f"At most {max_attachments} attachments are allowed per submission.",
            rule_code="TOO_MANY_ATTACHMENTS",
        )
    attempt_no = int(assignment.attempt_count or 0) + 1
    submission = TaskSubmission(
        assignment_id=assignment.id,
        attempt_no=attempt_no,
        description=description,
        submitted_by=actor_user_id,
    )
    session.add(submission)
    await session.flush()
    from app.modules.files import service as file_service

    for file_id in evidence_file_ids:
        await file_service.assert_exists(session, file_id)
        session.add(
            TaskAttachment(
                task_id=assignment.task_id,
                assignment_id=assignment.id,
                submission_id=submission.id,
                file_id=file_id,
                attachment_type="EVIDENCE",
                created_by=actor_user_id,
            )
        )
    assignment.status = "SUBMITTED"
    assignment.submitted_at = utcnow()
    assignment.attempt_count = attempt_no
    assignment.review_decision = None
    if task.status in {"ASSIGNED", "IN_PROGRESS"}:
        task.status = "SUBMITTED"
    await session.flush()
    return submission


async def review_submission(
    session: AsyncSession,
    *,
    submission: TaskSubmission,
    assignment: TaskAssignment,
    decision: str,
    actor_user_id: uuid.UUID,
    notes: str | None,
    settings: SettingsView,
) -> TaskAssignment:
    if submission.decision is not None:
        raise Conflict("This submission has already been reviewed.")
    if assignment.employee_id is not None:
        employee = await session.get(Employee, assignment.employee_id)
        if employee is not None and employee.user_id == actor_user_id and not settings.bool_(
            "tasks.allow_self_review"
        ):
            raise RuleViolation(
                "You cannot review your own submission.", rule_code="SELF_REVIEW_FORBIDDEN"
            )
    if decision in {"REJECTED", "RESUBMISSION_REQUESTED"} and not notes:
        raise ValidationError("Review notes are required when rejecting or requesting resubmission.")
    now = utcnow()
    submission.decision = decision
    submission.decided_by = actor_user_id
    submission.decided_at = now
    submission.decision_notes = notes
    task = await get_task(session, assignment.task_id)
    if decision == "APPROVED":
        assignment.status = "APPROVED"
        assignment.review_decision = "APPROVED"
        assignment.review_notes = notes
        assignment.reviewer_id = actor_user_id
        assignment.reviewed_at = now
    elif decision == "REJECTED":
        if settings.bool_("tasks.reopen_on_rejection"):
            assignment.status = "RESUBMISSION_REQUESTED"
        else:
            assignment.status = "REJECTED"
        assignment.review_decision = "REJECTED"
        assignment.review_notes = notes
        assignment.reviewer_id = actor_user_id
        assignment.reviewed_at = now
    else:
        assignment.status = "RESUBMISSION_REQUESTED"
        assignment.review_decision = "RESUBMISSION_REQUESTED"
        assignment.review_notes = notes
        assignment.reviewer_id = actor_user_id
        assignment.reviewed_at = now
    await session.flush()
    open_rows = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TaskAssignment)
                .where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.status.in_(list(OPEN_ASSIGNMENT)),
                )
            )
        ).scalar_one()
    )
    if open_rows == 0:
        approved = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(TaskAssignment)
                    .where(TaskAssignment.task_id == task.id, TaskAssignment.status == "APPROVED")
                )
            ).scalar_one()
        )
        task.status = "COMPLETED" if approved else "CANCELLED"
        task.completed_at = now if approved else None
        await session.flush()
    return assignment


async def cancel_task(
    session: AsyncSession, *, task: Task, actor_user_id: uuid.UUID, reason: str
) -> Task:
    if task.status in {"COMPLETED", "CANCELLED"}:
        raise RuleViolation("This task is already closed.", rule_code="TASK_CLOSED")
    task.status = "CANCELLED"
    task.cancelled_at = utcnow()
    task.cancel_reason = reason
    assignments = list(
        (
            await session.execute(
                select(TaskAssignment).where(
                    TaskAssignment.task_id == task.id,
                    TaskAssignment.status.in_(list(OPEN_ASSIGNMENT)),
                )
            )
        ).scalars().all()
    )
    for row in assignments:
        row.status = "CANCELLED"
    await session.flush()
    return task


async def add_comment(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    assignment_id: uuid.UUID | None,
    author_user_id: uuid.UUID,
    body: str,
    is_internal: bool,
) -> TaskComment:
    row = TaskComment(
        task_id=task_id,
        assignment_id=assignment_id,
        author_user_id=author_user_id,
        body=body,
        is_internal=is_internal,
    )
    session.add(row)
    await session.flush()
    return row


async def add_task_attachment(
    session: AsyncSession,
    *,
    task: Task,
    actor_user_id: uuid.UUID,
    file_id: uuid.UUID,
    attachment_type: str,
) -> TaskAttachment:
    from app.modules.files import service as file_service

    await file_service.assert_exists(session, file_id)
    row = TaskAttachment(
        task_id=task.id,
        file_id=file_id,
        attachment_type=attachment_type,
        created_by=actor_user_id,
    )
    session.add(row)
    await session.flush()
    return row


async def list_assignments(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[TaskAssignment], int]:
    conditions = []
    if employee_id is not None:
        conditions.append(TaskAssignment.employee_id == employee_id)
    if status:
        conditions.append(TaskAssignment.status == status)
    stmt = select(TaskAssignment).order_by(TaskAssignment.assigned_at.desc())
    count_stmt = select(func.count()).select_from(TaskAssignment)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def list_tasks(
    session: AsyncSession,
    *,
    status: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Task], int]:
    conditions = []
    if status:
        conditions.append(Task.status == status)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(func.lower(Task.title).like(pattern))
    stmt = select(Task).order_by(Task.created_at.desc())
    count_stmt = select(func.count()).select_from(Task)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def list_submissions(
    session: AsyncSession,
    *,
    decision: str | None = "PENDING",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[TaskSubmission], int]:
    conditions = []
    if decision:
        conditions.append(TaskSubmission.decision == decision)
    stmt = select(TaskSubmission).order_by(TaskSubmission.submitted_at.desc())
    count_stmt = select(func.count()).select_from(TaskSubmission)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def submission_evidence(session: AsyncSession, submission_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = list(
        (
            await session.execute(
                select(TaskAttachment).where(TaskAttachment.submission_id == submission_id)
            )
        ).scalars().all()
    )
    return [
        {
            "id": row.id,
            "file_id": row.file_id,
            "attachment_type": row.attachment_type,
            "created_at": row.created_at,
        }
        for row in rows
    ]


async def assignment_for_user(
    session: AsyncSession, assignment_id: uuid.UUID, *, employee_id: uuid.UUID
) -> TaskAssignment:
    row = await get_assignment(session, assignment_id)
    if row.employee_id != employee_id:
        raise NotFound("Task assignment not found.")
    return row