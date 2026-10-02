"""Complaints endpoints (docs/03_API_CONTRACT.md section 12)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.context import Ctx, require, require_any
from app.core.errors import NotFound, PermissionDenied, ValidationError
from app.core.pagination import PageParams, page_params, paginated
from app.modules.complaints import service

router = APIRouter(tags=["complaints"])


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    default_priority: str | None = None
    default_visibility: str | None = None
    sort_order: int = 0


class ComplaintCreate(BaseModel):
    category_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    priority: str | None = None
    visibility: str | None = None
    subject_employee_id: uuid.UUID | None = None


class ComplaintUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    priority: str | None = None
    visibility: str | None = None
    assigned_to: uuid.UUID | None = None
    category_id: uuid.UUID | None = None


class StatusChangeRequest(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=1000)
    internal_note: bool = False


class ResolveRequest(BaseModel):
    resolution_summary: str = Field(min_length=1, max_length=5000)


class CloseRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class RejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=1000)


class CommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    is_internal: bool = False


class AttachmentRequest(BaseModel):
    file_id: uuid.UUID
    note: str | None = Field(default=None, max_length=1000)


@router.get("/complaints/categories")
@router.get("/complaint-categories")
async def list_categories(ctx: Ctx = Depends(require("complaint.create.self"))) -> dict:
    rows = await service.list_categories(ctx.session, include_inactive=False)
    return {"items": [service.serialize_category(row) for row in rows]}


@router.post("/complaint-categories", status_code=201)
async def create_category(
    payload: CategoryCreate, ctx: Ctx = Depends(require("complaint.manage"))
) -> dict:
    from sqlalchemy import select as _select

    from app.modules.complaints.models import ComplaintCategory

    existing = (
        await ctx.session.execute(
            _select(ComplaintCategory).where(ComplaintCategory.code == payload.code.upper())
        )
    ).scalar_one_or_none()
    if existing is not None:
        from app.core.errors import DuplicateConflict

        raise DuplicateConflict(f"Complaint category {payload.code} already exists.")
    row = ComplaintCategory(**{**payload.model_dump(), "code": payload.code.upper()})
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.category.created",
        entity_type="complaint_category",
        entity_id=row.id,
    )
    return service.serialize_category(row)


@router.post("/complaints", status_code=201)
async def create_complaint(
    payload: ComplaintCreate, ctx: Ctx = Depends(require("complaint.create.self"))
) -> dict:
    row = await service.create_complaint(
        ctx.session,
        actor_user_id=ctx.actor_user_id,
        category_id=payload.category_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        visibility=payload.visibility,
        subject_employee_id=payload.subject_employee_id,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.created",
        entity_type="complaint",
        entity_id=row.id,
        after={"complaint_code": row.complaint_code, "status": row.status},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "complaint.created.v1",
        aggregate_type="complaint",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"complaint_code": row.complaint_code},
    )
    return service.serialize_complaint(row)


@router.get("/complaints/mine")
async def my_complaints(
    status: str | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("complaint.read.self")),
) -> dict:
    rows, total = await service.list_complaints(
        ctx.session, raised_by=ctx.actor_user_id, status=status, offset=params.offset, limit=params.page_size
    )
    return paginated([service.serialize_complaint(row) for row in rows], total, params)


@router.get("/complaints")
async def list_complaints(
    status: str | None = Query(None),
    priority: str | None = Query(None),
    category_id: uuid.UUID | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("complaint.read.all")),
) -> dict:
    rows, total = await service.list_complaints(
        ctx.session,
        status=status,
        priority=priority,
        category_id=category_id,
        assigned_to=assigned_to,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([service.serialize_complaint(row) for row in rows], total, params)


@router.get("/complaints/{complaint_id}")
async def get_complaint(complaint_id: uuid.UUID, ctx: Ctx = Depends(require("complaint.read.self"))) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    if row.raised_by != ctx.actor_user_id and not ctx.actor.has("complaint.read.all"):
        raise NotFound("Complaint not found.")
    return service.serialize_complaint(row)


@router.patch("/complaints/{complaint_id}")
async def update_complaint(
    complaint_id: uuid.UUID, payload: ComplaintUpdate, ctx: Ctx = Depends(require("complaint.manage"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    before, after = await service.update_complaint(
        ctx.session, complaint=row, changes=payload.model_dump(exclude_unset=True)
    )
    if before:
        await ctx.audit(
            category="COMPLAINT",
            action="complaint.updated",
            entity_type="complaint",
            entity_id=row.id,
            before={k: str(v) for k, v in before.items()},
            after={k: str(v) for k, v in after.items()},
        )
    return service.serialize_complaint(row)


@router.post("/complaints/{complaint_id}/status")
async def change_status(
    complaint_id: uuid.UUID, payload: StatusChangeRequest, ctx: Ctx = Depends(require("complaint.manage"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    await service.change_status(
        ctx.session,
        complaint=row,
        to_status=payload.to_status,
        actor_user_id=ctx.actor_user_id,
        reason=payload.reason,
        internal_note=payload.internal_note,
    )
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.status_changed",
        entity_type="complaint",
        entity_id=row.id,
        after={"status": row.status},
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "complaint.status_changed.v1",
        aggregate_type="complaint",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={"status": row.status},
    )
    return service.serialize_complaint(row)


@router.post("/complaints/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: uuid.UUID, payload: ResolveRequest, ctx: Ctx = Depends(require("complaint.resolve"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    await service.resolve_complaint(
        ctx.session, complaint=row, actor_user_id=ctx.actor_user_id, summary=payload.resolution_summary
    )
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.resolved",
        entity_type="complaint",
        entity_id=row.id,
        after={"status": row.status},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "complaint.resolved.v1",
        aggregate_type="complaint",
        aggregate_id=row.id,
        actor_user_id=ctx.actor_user_id,
        payload={},
    )
    return service.serialize_complaint(row)


@router.post("/complaints/{complaint_id}/close")
async def close_complaint(
    complaint_id: uuid.UUID, payload: CloseRequest, ctx: Ctx = Depends(require("complaint.close"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    await service.close_complaint(
        ctx.session, complaint=row, actor_user_id=ctx.actor_user_id, note=payload.note
    )
    await ctx.audit(
        category="COMPLAINT", action="complaint.closed", entity_type="complaint", entity_id=row.id
    )
    return service.serialize_complaint(row)


@router.post("/complaints/{complaint_id}/reject")
async def reject_complaint(
    complaint_id: uuid.UUID, payload: RejectRequest, ctx: Ctx = Depends(require("complaint.resolve"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    await service.reject_complaint(
        ctx.session, complaint=row, actor_user_id=ctx.actor_user_id, reason=payload.rejection_reason
    )
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.rejected",
        entity_type="complaint",
        entity_id=row.id,
        reason=payload.rejection_reason,
    )
    return service.serialize_complaint(row)


@router.get("/complaints/{complaint_id}/comments")
async def list_comments(
    complaint_id: uuid.UUID,
    include_internal: bool = Query(False),
    ctx: Ctx = Depends(require("complaint.read.self")),
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    if row.raised_by != ctx.actor_user_id and not ctx.actor.has("complaint.read.all"):
        raise NotFound("Complaint not found.")
    include = include_internal and ctx.actor.has("complaint.read.internal")
    rows = await service.list_comments(ctx.session, row.id, include_internal=include)
    return {"items": [service.serialize_comment(item) for item in rows]}


@router.post("/complaints/{complaint_id}/comments", status_code=201)
async def add_comment(
    complaint_id: uuid.UUID, payload: CommentRequest, ctx: Ctx = Depends(require("complaint.comment"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    if row.raised_by != ctx.actor_user_id and not ctx.actor.has("complaint.manage"):
        raise PermissionDenied("You may only comment on your own complaint.")
    comment = await service.add_comment(
        ctx.session,
        complaint=row,
        author_user_id=ctx.actor_user_id,
        body=payload.body,
        is_internal=payload.is_internal and ctx.actor.has("complaint.read.internal"),
    )
    return service.serialize_comment(comment)


@router.post("/complaints/{complaint_id}/attachments", status_code=201)
async def add_attachment(
    complaint_id: uuid.UUID, payload: AttachmentRequest, ctx: Ctx = Depends(require_any("complaint.comment", "complaint.manage"))
) -> dict:
    row = await service.get_complaint(ctx.session, complaint_id)
    if row.raised_by != ctx.actor_user_id and not ctx.actor.has("complaint.manage"):
        raise PermissionDenied("You may only attach files to your own complaint.")
    attachment = await service.add_attachment(
        ctx.session,
        complaint=row,
        actor_user_id=ctx.actor_user_id,
        file_id=payload.file_id,
        note=payload.note,
    )
    await ctx.audit(
        category="COMPLAINT",
        action="complaint.attachment_added",
        entity_type="complaint_attachment",
        entity_id=attachment.id,
    )
    return {"id": attachment.id, "complaint_id": attachment.complaint_id, "file_id": attachment.file_id}