"""Audit log writer and reader.

The writer participates in the caller's transaction so an audited state change and
its audit row commit or roll back together (docs/01_ARCHITECTURE.md section 16).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditRecord, RequestMeta, redact
from app.core.errors import NotFound
from app.modules.audit.models import AuditLog


def write_audit(session: AsyncSession, record: AuditRecord) -> AuditLog:
    """Add an audit row to the caller's transaction. Never commits."""
    record.sanitized()
    row = AuditLog(
        category=record.category,
        action=record.action,
        actor_user_id=record.actor_user_id,
        actor_type=record.actor_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        before=record.before,
        after=record.after,
        reason=record.reason,
        request_id=record.request_id,
        ip=record.ip,
        user_agent=(record.user_agent or None) and record.user_agent[:400],
    )
    session.add(row)
    return row


def audit(
    session: AsyncSession,
    *,
    category: str,
    action: str,
    entity_type: str,
    meta: RequestMeta | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_type: str = "USER",
    entity_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditLog:
    record = AuditRecord(
        category=category,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        before=redact(before),
        after=redact(after),
        reason=reason,
        request_id=meta.request_id if meta else None,
        ip=meta.ip if meta else None,
        user_agent=meta.user_agent if meta else None,
    )
    return write_audit(session, record)


def _apply_filters(
    stmt: Select[Any],
    *,
    category: str | None,
    action: str | None,
    entity_type: str | None,
    entity_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    from_: datetime | None,
    to: datetime | None,
    q: str | None,
) -> Select[Any]:
    conditions = []
    if category:
        conditions.append(AuditLog.category == category)
    if action:
        conditions.append(AuditLog.action == action)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_user_id:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if from_:
        conditions.append(AuditLog.created_at >= from_)
    if to:
        conditions.append(AuditLog.created_at < to)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            func.lower(AuditLog.action).like(pattern) | func.lower(AuditLog.entity_type).like(pattern)
        )
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return stmt


async def list_audit_logs(
    session: AsyncSession,
    *,
    category: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    q: str | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> tuple[list[AuditLog], int | None]:
    """Cursor pagination over descending id (docs/01_ARCHITECTURE.md 13.5)."""
    limit = max(1, min(limit, 200))
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit + 1)
    stmt = _apply_filters(
        stmt,
        category=category,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        from_=from_,
        to=to,
        q=q,
    )
    if cursor:
        stmt = stmt.where(AuditLog.id < cursor)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = rows[-1].id
    return rows, next_cursor


async def get_audit_log(session: AsyncSession, log_id: int) -> AuditLog:
    row = await session.get(AuditLog, log_id)
    if row is None:
        raise NotFound("Audit entry not found.")
    return row