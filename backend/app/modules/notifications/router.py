"""Notifications endpoints (docs/03_API_CONTRACT.md section 13)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from app.api.context import Ctx, require
from app.core.errors import NotFound
from app.modules.notifications import service

router = APIRouter(tags=["notifications"])


class ReadRequest(BaseModel):
    ids: list[uuid.UUID] | None = None
    all: bool = False


class PreferenceItem(BaseModel):
    event_type: str
    channel: str
    is_enabled: bool = True


class PreferencesRequest(BaseModel):
    preferences: list[PreferenceItem]


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str = Field(min_length=1, max_length=1000)
    keys: PushKeys


class BroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=2000)
    audience: str = "ALL"
    employee_ids: list[uuid.UUID] | None = None


@router.get("/notifications")
async def list_notifications(
    is_read: bool | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(require("notification.read.self")),
) -> dict:
    cursor_value = int(cursor) if cursor and cursor.isdigit() else None
    rows, next_cursor = await service.list_notifications(
        ctx.session, user_id=ctx.actor_user_id, is_read=is_read, cursor=cursor_value, limit=limit
    )
    return {
        "items": [service.serialize_notification(row) for row in rows],
        "next_cursor": str(next_cursor) if next_cursor else None,
    }


@router.get("/notifications/unread-count")
async def unread_count(ctx: Ctx = Depends(require("notification.read.self"))) -> dict:
    return {"unread": await service.unread_count(ctx.session, ctx.actor_user_id)}


@router.post("/notifications/read")
async def mark_read(payload: ReadRequest, ctx: Ctx = Depends(require("notification.read.self"))) -> dict:
    updated = await service.mark_read(
        ctx.session,
        user_id=ctx.actor_user_id,
        notification_id=None,
        ids=payload.ids,
        all_=payload.all,
    )
    return {"updated": updated}


@router.post("/notifications/{notification_id}/read")
async def mark_one_read(
    notification_id: uuid.UUID, ctx: Ctx = Depends(require("notification.read.self"))
) -> dict:
    updated = await service.mark_read(
        ctx.session,
        user_id=ctx.actor_user_id,
        notification_id=notification_id,
        ids=None,
        all_=False,
    )
    if not updated:
        raise NotFound("Notification not found.")
    return {"updated": updated}


@router.get("/notification-preferences")
async def list_preferences(ctx: Ctx = Depends(require("notification.read.self"))) -> dict:
    rows = await service.list_preferences(ctx.session, ctx.actor_user_id)
    return {"items": [service.serialize_preference(row) for row in rows]}


@router.patch("/notification-preferences")
async def set_preferences(
    payload: PreferencesRequest, ctx: Ctx = Depends(require("notification.read.self"))
) -> dict:
    rows = await service.set_preferences(
        ctx.session,
        user_id=ctx.actor_user_id,
        preferences=[item.model_dump() for item in payload.preferences],
        settings=ctx.settings,
    )
    return {"items": [service.serialize_preference(row) for row in rows]}


@router.post("/push-subscriptions", status_code=201)
async def add_subscription(
    payload: PushSubscriptionRequest, ctx: Ctx = Depends(require("notification.read.self"))
) -> dict:
    row = await service.add_subscription(
        ctx.session,
        user_id=ctx.actor_user_id,
        endpoint=payload.endpoint,
        p256dh_key=payload.keys.p256dh,
        auth_key=payload.keys.auth,
        user_agent=ctx.meta.user_agent,
    )
    return service.serialize_subscription(row)


@router.delete("/push-subscriptions/{subscription_id}", status_code=204)
async def remove_subscription(
    subscription_id: uuid.UUID, ctx: Ctx = Depends(require("notification.read.self"))
) -> Response:
    await service.remove_subscription(
        ctx.session, user_id=ctx.actor_user_id, subscription_id=subscription_id
    )
    await ctx.audit(
        category="SECURITY",
        action="notification.push_subscription.removed",
        entity_type="push_subscription",
        entity_id=subscription_id,
    )
    return Response(status_code=204)


@router.post("/notifications/broadcast", status_code=201)
async def broadcast(payload: BroadcastRequest, ctx: Ctx = Depends(require("notification.manage"))) -> dict:
    from sqlalchemy import select

    from app.modules.directory.models import Employee

    if payload.audience == "SELECTED" and payload.employee_ids:
        employees = list(
            (
                await ctx.session.execute(
                    select(Employee).where(Employee.id.in_(payload.employee_ids))
                )
            ).scalars().all()
        )
    else:
        employees = list(
            (
                await ctx.session.execute(
                    select(Employee).where(Employee.employment_status == "ACTIVE")
                )
            ).scalars().all()
        )
    created = 0
    for employee in employees:
        await service.notify(
            ctx.session,
            recipient_user_id=employee.user_id,
            event_type="admin.broadcast",
            title=payload.title,
            body=payload.body,
            entity_type="broadcast",
            priority="NORMAL",
            settings=ctx.settings,
        )
        created += 1
    await ctx.audit(
        category="SECURITY",
        action="notification.broadcast",
        entity_type="broadcast",
        after={"recipients": created},
    )
    return {"recipients": created}