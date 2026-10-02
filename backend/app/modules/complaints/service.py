"""Complaints service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, DuplicateConflict, NotFound, RuleViolation, ValidationError
from app.core.timeutil import utcnow
from app.modules.complaints.models import (
    Complaint,
    ComplaintAttachment,
    ComplaintCategory,
    ComplaintComment,
    ComplaintStatusHistory,
)
from app.modules.settings.service import SettingsView

TERMINAL_STATUS = frozenset({"CLOSED", "REJECTED"})
ALLOWED_STATUSES = frozenset(
    {"OPEN", "IN_REVIEW", "ACTION_REQUIRED", "RESOLVED", "CLOSED", "REJECTED"}
)
PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "URGENT"})


def serialize_category(row: ComplaintCategory) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "default_priority": row.default_priority,
        "default_visibility": row.default_visibility,
        "is_active": row.is_active,
        "sort_order": row.sort_order,
    }


def serialize_complaint(row: Complaint) -> dict[str, Any]:
    return {
        "id": row.id,
        "complaint_code": row.complaint_code,
        "category_id": row.category_id,
        "title": row.title,
        "description": row.description,
        "priority": row.priority,
        "status": row.status,
        "visibility": row.visibility,
        "raised_by": row.raised_by,
        "subject_employee_id": row.subject_employee_id,
        "assigned_to": row.assigned_to,
        "resolution_summary": row.resolution_summary,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at,
        "closed_by": row.closed_by,
        "closed_at": row.closed_at,
        "rejection_reason": row.rejection_reason,
        "sla_due_at": row.sla_due_at,
        "version": row.version,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def serialize_comment(row: ComplaintComment) -> dict[str, Any]:
    return {
        "id": row.id,
        "complaint_id": row.complaint_id,
        "author_user_id": row.author_user_id,
        "body": row.body,
        "is_internal": row.is_internal,
        "created_at": row.created_at,
    }


async def get_complaint(session: AsyncSession, complaint_id: uuid.UUID) -> Complaint:
    row = await session.get(Complaint, complaint_id)
    if row is None:
        raise NotFound("Complaint not found.")
    return row


async def get_category(session: AsyncSession, category_id: uuid.UUID) -> ComplaintCategory:
    row = await session.get(ComplaintCategory, category_id)
    if row is None:
        raise NotFound("Complaint category not found.")
    return row


async def list_categories(session: AsyncSession, *, include_inactive: bool = False) -> list[ComplaintCategory]:
    stmt = select(ComplaintCategory).order_by(ComplaintCategory.sort_order, ComplaintCategory.code)
    if not include_inactive:
        stmt = stmt.where(ComplaintCategory.is_active.is_(True))
    return list((await session.execute(stmt)).scalars().all())


def _generate_code() -> str:
    return f"CMP-{utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


async def create_complaint(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    category_id: uuid.UUID,
    title: str,
    description: str,
    priority: str | None,
    visibility: str | None,
    subject_employee_id: uuid.UUID | None,
    settings: SettingsView,
) -> Complaint:
    if not settings.bool_("complaints.enabled"):
        raise RuleViolation("Complaints are disabled.", rule_code="COMPLAINTS_DISABLED")
    category = await get_category(session, category_id)
    if not category.is_active:
        raise RuleViolation("This complaint category is not available.")
    if subject_employee_id is not None and not settings.bool_("complaints.employee_may_reference_employee"):
        subject_employee_id = None
    now = utcnow()
    sla_hours = settings.int_("complaints.sla_hours")
    row = Complaint(
        complaint_code=_generate_code(),
        category_id=category.id,
        title=title,
        description=description,
        priority=priority or category.default_priority or settings.str_("complaints.default_priority"),
        status="OPEN",
        visibility=visibility or category.default_visibility or settings.str_("complaints.default_visibility"),
        raised_by=actor_user_id,
        subject_employee_id=subject_employee_id,
        sla_due_at=now + timedelta(hours=sla_hours) if sla_hours else None,
    )
    session.add(row)
    await session.flush()
    session.add(
        ComplaintStatusHistory(
            complaint_id=row.id,
            from_status=None,
            to_status="OPEN",
            changed_by=actor_user_id,
            reason="Complaint submitted.",
        )
    )
    await session.flush()
    return row


async def change_status(
    session: AsyncSession,
    *,
    complaint: Complaint,
    to_status: str,
    actor_user_id: uuid.UUID,
    reason: str | None,
    internal_note: bool,
) -> Complaint:
    if to_status not in ALLOWED_STATUSES:
        raise ValidationError(f"Unsupported status: {to_status}")
    if complaint.status in TERMINAL_STATUS:
        raise Conflict(f"This complaint is already {complaint.status}.")
    previous = complaint.status
    complaint.status = to_status
    complaint.version = int(complaint.version or 1) + 1
    complaint.updated_at = utcnow()
    session.add(
        ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=previous,
            to_status=to_status,
            changed_by=actor_user_id,
            reason=reason,
            is_internal_note=internal_note,
        )
    )
    await session.flush()
    return complaint


async def resolve_complaint(
    session: AsyncSession, *, complaint: Complaint, actor_user_id: uuid.UUID, summary: str
) -> Complaint:
    if complaint.status in TERMINAL_STATUS:
        raise Conflict(f"This complaint is already {complaint.status}.")
    previous = complaint.status
    now = utcnow()
    complaint.status = "RESOLVED"
    complaint.resolution_summary = summary
    complaint.resolved_by = actor_user_id
    complaint.resolved_at = now
    complaint.updated_at = now
    complaint.version = int(complaint.version or 1) + 1
    session.add(
        ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=previous,
            to_status="RESOLVED",
            changed_by=actor_user_id,
            reason=summary,
        )
    )
    await session.flush()
    return complaint


async def close_complaint(
    session: AsyncSession, *, complaint: Complaint, actor_user_id: uuid.UUID, note: str | None
) -> Complaint:
    if complaint.status != "RESOLVED":
        raise Conflict("Only a resolved complaint can be closed.")
    previous = complaint.status
    now = utcnow()
    complaint.status = "CLOSED"
    complaint.closed_by = actor_user_id
    complaint.closed_at = now
    complaint.updated_at = now
    complaint.version = int(complaint.version or 1) + 1
    session.add(
        ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=previous,
            to_status="CLOSED",
            changed_by=actor_user_id,
            reason=note,
        )
    )
    await session.flush()
    return complaint


async def reject_complaint(
    session: AsyncSession, *, complaint: Complaint, actor_user_id: uuid.UUID, reason: str
) -> Complaint:
    if complaint.status in TERMINAL_STATUS:
        raise Conflict(f"This complaint is already {complaint.status}.")
    previous = complaint.status
    now = utcnow()
    complaint.status = "REJECTED"
    complaint.rejection_reason = reason
    complaint.resolved_by = actor_user_id
    complaint.resolved_at = now
    complaint.updated_at = now
    complaint.version = int(complaint.version or 1) + 1
    session.add(
        ComplaintStatusHistory(
            complaint_id=complaint.id,
            from_status=previous,
            to_status="REJECTED",
            changed_by=actor_user_id,
            reason=reason,
        )
    )
    await session.flush()
    return complaint


async def update_complaint(
    session: AsyncSession, *, complaint: Complaint, changes: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in ("title", "description", "priority", "visibility", "assigned_to", "category_id"):
        if field not in changes:
            continue
        value = changes[field]
        if field == "priority" and value is not None and value not in PRIORITIES:
            raise ValidationError(f"Unsupported priority: {value}")
        before[field] = getattr(complaint, field)
        setattr(complaint, field, value)
        after[field] = value
    if before:
        complaint.updated_at = utcnow()
        complaint.version = int(complaint.version or 1) + 1
        await session.flush()
    return before, after


async def add_comment(
    session: AsyncSession,
    *,
    complaint: Complaint,
    author_user_id: uuid.UUID,
    body: str,
    is_internal: bool,
) -> ComplaintComment:
    if complaint.status in TERMINAL_STATUS:
        from app.modules.settings import service as settings_module

        raise Conflict("This complaint is closed; commenting is disabled.")
    row = ComplaintComment(
        complaint_id=complaint.id, author_user_id=author_user_id, body=body, is_internal=is_internal
    )
    session.add(row)
    await session.flush()
    return row


async def list_comments(
    session: AsyncSession, complaint_id: uuid.UUID, *, include_internal: bool
) -> list[ComplaintComment]:
    stmt = (
        select(ComplaintComment)
        .where(ComplaintComment.complaint_id == complaint_id)
        .order_by(ComplaintComment.created_at)
    )
    if not include_internal:
        stmt = stmt.where(ComplaintComment.is_internal.is_(False))
    return list((await session.execute(stmt)).scalars().all())


async def add_attachment(
    session: AsyncSession,
    *,
    complaint: Complaint,
    actor_user_id: uuid.UUID,
    file_id: uuid.UUID,
    note: str | None,
) -> ComplaintAttachment:
    from app.modules.files import service as file_service

    await file_service.assert_exists(session, file_id)
    row = ComplaintAttachment(
        complaint_id=complaint.id, file_id=file_id, uploaded_by=actor_user_id, note=note
    )
    session.add(row)
    await session.flush()
    return row


async def list_complaints(
    session: AsyncSession,
    *,
    raised_by: uuid.UUID | None = None,
    status: str | None = None,
    priority: str | None = None,
    category_id: uuid.UUID | None = None,
    assigned_to: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Complaint], int]:
    conditions = []
    if raised_by:
        conditions.append(Complaint.raised_by == raised_by)
    if status:
        conditions.append(Complaint.status == status)
    if priority:
        conditions.append(Complaint.priority == priority)
    if category_id:
        conditions.append(Complaint.category_id == category_id)
    if assigned_to:
        conditions.append(Complaint.assigned_to == assigned_to)
    stmt = select(Complaint).order_by(Complaint.created_at.desc())
    count_stmt = select(func.count()).select_from(Complaint)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total