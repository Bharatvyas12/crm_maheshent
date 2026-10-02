"""Tasks endpoints (docs/03_API_CONTRACT.md section 8)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from app.api.context import Ctx, get_ctx, require, require_any
from app.api.idempotency import begin_idempotency, finish_idempotency, replay_response
from app.core.errors import Conflict, NotFound, PermissionDenied, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.core.timeutil import utcnow
from app.modules.directory import service as directory_service
from app.modules.tasks import service

router = APIRouter(tags=["tasks"])


class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: str = "NORMAL"
    due_at: datetime | None = None
    requires_evidence: bool | None = None
    requires_attachment: bool | None = None
    employee_ids: list[uuid.UUID] = Field(default_factory=list)


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: str | None = None
    due_at: datetime | None = None
    requires_evidence: bool | None = None
    requires_attachment: bool | None = None


class TaskCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AssignmentCreateRequest(BaseModel):
    employee_ids: list[uuid.UUID]


class SubmissionCreateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=5000)
    evidence_file_ids: list[uuid.UUID] = Field(default_factory=list)


class ReviewDecisionRequest(BaseModel):
    review_notes: str | None = Field(default=None, max_length=2000)


class CommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    is_internal: bool = False
    assignment_id: uuid.UUID | None = None


class AttachmentCreateRequest(BaseModel):
    file_id: uuid.UUID
    attachment_type: str = "BRIEF"


PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}


@router.get("/tasks")
async def list_tasks(
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("task.read.all")),
) -> dict:
    rows, total = await service.list_tasks(
        ctx.session, status=status, q=q, offset=params.offset, limit=params.page_size
    )
    return paginated([service.serialize_task(row) for row in rows], total, params)


@router.post("/tasks", status_code=201)
async def create_task(
    payload: TaskCreateRequest, ctx: Ctx = Depends(require("task.create"))
) -> dict:
    if payload.priority not in PRIORITIES:
        raise ValidationError(f"Unsupported priority: {payload.priority}")
    task, assignments = await service.create_task(
        ctx.session,
        actor_user_id=ctx.actor_user_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_at=payload.due_at,
        requires_evidence=payload.requires_evidence,
        requires_attachment=payload.requires_attachment,
        employee_ids=payload.employee_ids,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="TASK",
        action="task.created",
        entity_type="task",
        entity_id=task.id,
        after={"title": task.title, "assignees": [str(a.employee_id) for a in assignments]},
    )
    from app.platform.service import emit_event

    for assignment in assignments:
        emit_event(
            ctx.session,
            "task.assigned.v1",
            aggregate_type="task_assignment",
            aggregate_id=assignment.id,
            actor_user_id=ctx.actor_user_id,
            payload={"task_id": str(task.id), "employee_id": str(assignment.employee_id)},
        )
    return {
        **service.serialize_task(task),
        "assignments": [service.serialize_assignment(row) for row in assignments],
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, ctx: Ctx = Depends(require("task.read.self"))) -> dict:
    task = await service.get_task(ctx.session, task_id)
    rows, _total = await service.list_assignments(
        ctx.session, employee_id=None, status=None, limit=100
    )
    scoped = [row for row in rows if row.task_id == task.id]
    if not ctx.actor.has("task.read.all"):
        if not any(row.employee_id == ctx.actor.employee_id for row in scoped):
            raise NotFound("Task not found.")
    can_review = ctx.actor.has("task.review")
    return {
        **service.serialize_task(task),
        "assignments": [
            service.serialize_assignment(
                row,
                task,
                transitions=service.allowed_transitions(
                    row, is_assignee=row.employee_id == ctx.actor.employee_id, can_review=can_review
                ),
            )
            for row in scoped
        ],
    }


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: uuid.UUID, payload: TaskUpdateRequest, ctx: Ctx = Depends(require("task.update"))
) -> dict:
    task = await service.get_task(ctx.session, task_id)
    if task.status in {"COMPLETED", "CANCELLED"}:
        raise Conflict("A closed task cannot be edited.")
    changes = payload.model_dump(exclude_unset=True)
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise ValidationError(f"Unsupported priority: {changes['priority']}")
    for field, value in changes.items():
        setattr(task, field, value)
    await ctx.session.flush()
    await ctx.audit(
        category="TASK", action="task.updated", entity_type="task", entity_id=task.id, after=changes
    )
    return service.serialize_task(task)


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: uuid.UUID, payload: TaskCancelRequest, ctx: Ctx = Depends(require("task.cancel"))
) -> dict:
    task = await service.get_task(ctx.session, task_id)
    await service.cancel_task(
        ctx.session, task=task, actor_user_id=ctx.actor_user_id, reason=payload.reason
    )
    await ctx.audit(
        category="TASK",
        action="task.cancelled",
        entity_type="task",
        entity_id=task.id,
        reason=payload.reason,
    )
    return service.serialize_task(task)


@router.post("/tasks/{task_id}/assignments", status_code=201)
async def add_assignments(
    task_id: uuid.UUID, payload: AssignmentCreateRequest, ctx: Ctx = Depends(require("task.assign"))
) -> dict:
    task = await service.get_task(ctx.session, task_id)
    if task.status in {"COMPLETED", "CANCELLED"}:
        raise Conflict("A closed task cannot receive new assignments.")
    rows = await service.assign_employees(
        ctx.session,
        task=task,
        employee_ids=payload.employee_ids,
        actor_user_id=ctx.actor_user_id,
    )
    await ctx.audit(
        category="TASK",
        action="task.assignments_added",
        entity_type="task",
        entity_id=task.id,
        after={"assignees": [str(row.employee_id) for row in rows]},
    )
    return {"items": [service.serialize_assignment(row, task) for row in rows]}


@router.delete("/tasks/{task_id}/assignments/{assignment_id}", status_code=204)
async def remove_assignment(
    task_id: uuid.UUID, assignment_id: uuid.UUID, ctx: Ctx = Depends(require("task.assign"))
) -> Response:
    assignment = await service.get_assignment(ctx.session, assignment_id)
    if assignment.task_id != task_id:
        raise NotFound("Assignment not found.")
    if assignment.status in {"APPROVED", "REJECTED"}:
        raise Conflict("A reviewed assignment cannot be removed.")
    assignment.status = "CANCELLED"
    await ctx.session.flush()
    await ctx.audit(
        category="TASK",
        action="task.assignment_removed",
        entity_type="task_assignment",
        entity_id=assignment.id,
    )
    return Response(status_code=204)


@router.post("/tasks/{task_id}/attachments", status_code=201)
async def add_task_attachment(
    task_id: uuid.UUID, payload: AttachmentCreateRequest, ctx: Ctx = Depends(require("task.update"))
) -> dict:
    task = await service.get_task(ctx.session, task_id)
    row = await service.add_task_attachment(
        ctx.session,
        task=task,
        actor_user_id=ctx.actor_user_id,
        file_id=payload.file_id,
        attachment_type=payload.attachment_type,
    )
    await ctx.audit(
        category="TASK",
        action="task.attachment_added",
        entity_type="task_attachment",
        entity_id=row.id,
    )
    return {"id": row.id, "task_id": row.task_id, "file_id": row.file_id, "attachment_type": row.attachment_type}


@router.post("/tasks/{task_id}/comments", status_code=201)
async def comment_on_task(
    task_id: uuid.UUID, payload: CommentCreateRequest, ctx: Ctx = Depends(require_any("task.review", "task.update", "task.comment"))
) -> dict:
    task = await service.get_task(ctx.session, task_id)
    row = await service.add_comment(
        ctx.session,
        task_id=task.id,
        assignment_id=payload.assignment_id,
        author_user_id=ctx.actor_user_id,
        body=payload.body,
        is_internal=payload.is_internal and ctx.actor.has("task.review"),
    )
    return service.serialize_comment(row)

@router.get("/task-assignments/mine")
async def my_assignments(
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("task.read.self")),
) -> dict:
    rows, total = await service.list_assignments(
        ctx.session,
        employee_id=ctx.employee_id,
        status=status,
        offset=params.offset,
        limit=params.page_size,
    )
    can_review = ctx.actor.has("task.review")
    items = []
    for row in rows:
        task = await service.get_task(ctx.session, row.task_id)
        items.append(
            service.serialize_assignment(
                row, task, transitions=service.allowed_transitions(row, is_assignee=True, can_review=can_review)
            )
        )
    return paginated(items, total, params)


@router.get("/task-assignments/{assignment_id}")
async def get_assignment(
    assignment_id: uuid.UUID, ctx: Ctx = Depends(require_any("task.read.self", "task.read.all"))
) -> dict:
    row = await service.get_assignment(ctx.session, assignment_id)
    if row.employee_id != ctx.actor.employee_id and not ctx.actor.has("task.read.all"):
        raise NotFound("Task assignment not found.")
    task = await service.get_task(ctx.session, row.task_id)
    return service.serialize_assignment(
        row,
        task,
        transitions=service.allowed_transitions(
            row,
            is_assignee=row.employee_id == ctx.actor.employee_id,
            can_review=ctx.actor.has("task.review"),
        ),
    )


@router.post("/task-assignments/{assignment_id}/start")
async def start_assignment(
    assignment_id: uuid.UUID, ctx: Ctx = Depends(require("task.submit.self"))
) -> dict:
    row = await service.assignment_for_user(ctx.session, assignment_id, employee_id=ctx.employee_id)
    await service.start_assignment(ctx.session, row, actor_user_id=ctx.actor_user_id)
    await ctx.audit(
        category="TASK",
        action="task.started",
        entity_type="task_assignment",
        entity_id=row.id,
    )
    return service.serialize_assignment(row)


@router.post("/task-assignments/{assignment_id}/complete")
async def complete_assignment(
    assignment_id: uuid.UUID, ctx: Ctx = Depends(require("task.submit.self"))
) -> dict:
    row = await service.assignment_for_user(ctx.session, assignment_id, employee_id=ctx.employee_id)
    await service.complete_assignment(ctx.session, row)
    return service.serialize_assignment(row)


@router.post("/task-assignments/{assignment_id}/submissions", status_code=201)
async def submit_assignment(
    assignment_id: uuid.UUID,
    payload: SubmissionCreateRequest,
    request: Request,
    ctx: Ctx = Depends(require("task.submit.self")),
) -> dict:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint="task-assignments.submit", payload=payload.model_dump(mode="json")
    )
    if replay is not None:
        return replay_response(replay)
    row = await service.assignment_for_user(ctx.session, assignment_id, employee_id=ctx.employee_id)
    submission = await service.submit_assignment(
        ctx.session,
        assignment=row,
        actor_user_id=ctx.actor_user_id,
        description=payload.description,
        evidence_file_ids=payload.evidence_file_ids,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="TASK",
        action="task.submitted",
        entity_type="task_submission",
        entity_id=submission.id,
        after={"attempt_no": submission.attempt_no},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "task.submitted.v1",
        aggregate_type="task_assignment",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"submission_id": str(submission.id)},
    )
    body = service.serialize_submission(
        submission, evidence=await service.submission_evidence(ctx.session, submission.id)
    )
    await finish_idempotency(guard, 201, body)
    return body


@router.post("/task-assignments/{assignment_id}/comments", status_code=201)
async def comment_on_assignment(
    assignment_id: uuid.UUID, payload: CommentCreateRequest, ctx: Ctx = Depends(require("task.comment"))
) -> dict:
    row = await service.get_assignment(ctx.session, assignment_id)
    if row.employee_id != ctx.actor.employee_id and not ctx.actor.has("task.read.all"):
        raise NotFound("Task assignment not found.")
    comment = await service.add_comment(
        ctx.session,
        task_id=row.task_id,
        assignment_id=row.id,
        author_user_id=ctx.actor_user_id,
        body=payload.body,
        is_internal=payload.is_internal and ctx.actor.has("task.review"),
    )
    return service.serialize_comment(comment)


@router.get("/task-submissions")
async def list_submissions(
    decision: str | None = Query("PENDING"),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("task.review")),
) -> dict:
    rows, total = await service.list_submissions(
        ctx.session, decision=decision, offset=params.offset, limit=params.page_size
    )
    items = []
    for row in rows:
        items.append(
            service.serialize_submission(
                row, evidence=await service.submission_evidence(ctx.session, row.id)
            )
        )
    return paginated(items, total, params)


async def _review(
    ctx: Ctx, submission_id: uuid.UUID, decision: str, payload: ReviewDecisionRequest
) -> dict:
    submission = await service.get_submission(ctx.session, submission_id)
    assignment = await service.get_assignment(ctx.session, submission.assignment_id)
    await service.review_submission(
        ctx.session,
        submission=submission,
        assignment=assignment,
        decision=decision,
        actor_user_id=ctx.actor_user_id,
        notes=payload.review_notes,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="TASK",
        action=f"task.review.{decision.lower()}",
        entity_type="task_submission",
        entity_id=submission.id,
        after={"decision": decision},
        reason=payload.review_notes,
    )
    from app.platform.service import emit_event

    event_type = {
        "APPROVED": "task.approved.v1",
        "REJECTED": "task.rejected.v1",
        "RESUBMISSION_REQUESTED": "task.resubmission_requested.v1",
    }[decision]
    emit_event(
        ctx.session,
        event_type,
        aggregate_type="task_assignment",
        aggregate_id=assignment.id,
        actor_user_id=ctx.actor_user_id,
        payload={"submission_id": str(submission.id)},
    )
    return service.serialize_submission(submission)


@router.post("/task-submissions/{submission_id}/approve")
async def approve_submission(
    submission_id: uuid.UUID, payload: ReviewDecisionRequest, ctx: Ctx = Depends(require("task.review"))
) -> dict:
    return await _review(ctx, submission_id, "APPROVED", payload)


@router.post("/task-submissions/{submission_id}/reject")
async def reject_submission(
    submission_id: uuid.UUID, payload: ReviewDecisionRequest, ctx: Ctx = Depends(require("task.review"))
) -> dict:
    if not payload.review_notes:
        raise ValidationError("Review notes are required when rejecting a submission.")
    return await _review(ctx, submission_id, "REJECTED", payload)


@router.post("/task-submissions/{submission_id}/request-resubmission")
async def request_resubmission(
    submission_id: uuid.UUID, payload: ReviewDecisionRequest, ctx: Ctx = Depends(require("task.review"))
) -> dict:
    if not payload.review_notes:
        raise ValidationError("Review notes are required when requesting a resubmission.")
    return await _review(ctx, submission_id, "RESUBMISSION_REQUESTED", payload)