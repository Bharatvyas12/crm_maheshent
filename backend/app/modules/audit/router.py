"""Audit endpoints (docs/03_API_CONTRACT.md section 16)."""

from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.api.context import Ctx, parse_datetime, require
from app.core.pagination import PageParams, page_params, paginated
from app.modules.audit import service

router = APIRouter(tags=["audit"])


class AuditExportRequest(BaseModel):
    format: str = "CSV"
    filters: dict = {}


def _payload(row) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "action": row.action,
        "actor_user_id": row.actor_user_id,
        "actor_type": row.actor_type,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "before": row.before,
        "after": row.after,
        "reason": row.reason,
        "request_id": row.request_id,
        "ip": str(row.ip) if row.ip else None,
        "user_agent": row.user_agent,
        "created_at": row.created_at,
    }


@router.get("/audit-logs")
async def list_audit_logs(
    category: str | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    entity_id: uuid.UUID | None = Query(None),
    actor_user_id: uuid.UUID | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require("audit.read")),
) -> dict:
    cursor_value = int(cursor) if cursor and cursor.lstrip("-").isdigit() else None
    rows, next_cursor = await service.list_audit_logs(
        ctx.session,
        category=category,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        from_=parse_datetime(from_, "from"),
        to=parse_datetime(to, "to"),
        q=q,
        cursor=cursor_value,
        limit=limit,
    )
    return {
        "items": [_payload(row) for row in rows],
        "next_cursor": str(next_cursor) if next_cursor else None,
    }


@router.get("/audit-logs/{log_id}")
async def get_audit_log(log_id: int, ctx: Ctx = Depends(require("audit.read"))) -> dict:
    row = await service.get_audit_log(ctx.session, log_id)
    return _payload(row)


@router.post("/audit-logs/exports", status_code=201)
async def export_audit_logs(
    payload: AuditExportRequest, ctx: Ctx = Depends(require("audit.export"))
) -> Response:
    filters = payload.filters or {}
    rows, _next = await service.list_audit_logs(
        ctx.session,
        category=filters.get("category"),
        action=filters.get("action"),
        entity_type=filters.get("entity_type"),
        entity_id=uuid.UUID(filters["entity_id"]) if filters.get("entity_id") else None,
        actor_user_id=uuid.UUID(filters["actor_user_id"]) if filters.get("actor_user_id") else None,
        from_=parse_datetime(filters.get("from"), "from"),
        to=parse_datetime(filters.get("to"), "to"),
        q=filters.get("q"),
        limit=200,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "created_at", "category", "action", "actor_user_id", "entity_type", "entity_id", "reason"]
    )
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat(),
                row.category,
                row.action,
                str(row.actor_user_id) if row.actor_user_id else "",
                row.entity_type,
                str(row.entity_id) if row.entity_id else "",
                row.reason or "",
            ]
        )
    await ctx.audit(
        category="SECURITY",
        action="audit.exported",
        entity_type="audit_log",
        after={"rows": len(rows)},
    )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit-logs.csv"'},
    )