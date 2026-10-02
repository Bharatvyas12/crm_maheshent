"""Notifications service: in-app inbox, preferences, push subscriptions, delivery.

The module never mutates domain state; it reacts to domain events (architecture 7.5).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, RuleViolation, ValidationError
from app.core.timeutil import utcnow
from app.modules.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationPreference,
    PushSubscription,
)
from app.modules.settings.service import SettingsView


def serialize_notification(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "recipient_user_id": row.recipient_user_id,
        "event_type": row.event_type,
        "title": row.title,
        "body": row.body,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "data": row.data,
        "priority": row.priority,
        "is_read": row.is_read,
        "read_at": row.read_at,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
    }


def serialize_preference(row: NotificationPreference) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "event_type": row.event_type,
        "channel": row.channel,
        "is_enabled": row.is_enabled,
        "updated_at": row.updated_at,
    }


def serialize_subscription(row: PushSubscription) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "endpoint": row.endpoint,
        "user_agent": row.user_agent,
        "is_active": row.is_active,
        "failure_count": row.failure_count,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


async def notify(
    session: AsyncSession,
    *,
    recipient_user_id: uuid.UUID,
    event_type: str,
    title: str,
    body: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    priority: str = "NORMAL",
    channels: list[str] | None = None,
    settings: SettingsView | None = None,
) -> Notification:
    row = Notification(
        recipient_user_id=recipient_user_id,
        event_type=event_type,
        title=title[:200],
        body=body,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data or {},
        priority=priority,
    )
    session.add(row)
    await session.flush()
    enabled = channels
    if enabled is None and settings is not None:
        enabled = list(settings.json_("notifications.channels_enabled") or ["IN_APP"])
    for channel in enabled or ["IN_APP"]:
        session.add(
            NotificationDelivery(
                notification_id=row.id, channel=channel, status="PENDING", attempts=0
            )
        )
    await session.flush()
    return row


async def list_notifications(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_read: bool | None = None,
    cursor: int | None = None,
    limit: int = 50,
) -> tuple[list[Notification], int | None]:
    limit = max(1, min(limit, 200))
    stmt = (
        select(Notification)
        .where(Notification.recipient_user_id == user_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit + 1)
    )
    if is_read is not None:
        stmt = stmt.where(Notification.is_read.is_(is_read))
    if cursor:
        stmt = stmt.where(
            Notification.created_at
            <= func.to_timestamp(cursor / 1000.0)
        )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = int(rows[-1].created_at.timestamp() * 1000)
    return rows, next_cursor


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.recipient_user_id == user_id, Notification.is_read.is_(False))
            )
        ).scalar_one()
    )


async def mark_read(
    session: AsyncSession, *, user_id: uuid.UUID, notification_id: uuid.UUID | None, ids: list[uuid.UUID] | None, all_: bool
) -> int:
    target = (
        update(Notification)
        .where(Notification.recipient_user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=utcnow())
    )
    if notification_id is not None:
        target = target.where(Notification.id == notification_id)
    elif ids:
        target = target.where(Notification.id.in_(ids))
    elif not all_:
        raise ValidationError("Provide ids, all=true, or a notification id.")
    result = await session.execute(target)
    await session.flush()
    return int(result.rowcount or 0)


async def list_preferences(session: AsyncSession, user_id: uuid.UUID) -> list[NotificationPreference]:
    return list(
        (
            await session.execute(
                select(NotificationPreference)
                .where(NotificationPreference.user_id == user_id)
                .order_by(NotificationPreference.event_type, NotificationPreference.channel)
            )
        ).scalars().all()
    )


async def set_preferences(
    session: AsyncSession, *, user_id: uuid.UUID, preferences: list[dict[str, Any]], settings: SettingsView
) -> list[NotificationPreference]:
    allowed_channels = set(settings.json_("notifications.channels_enabled") or [])
    for item in preferences:
        event_type = item.get("event_type")
        channel = item.get("channel")
        if not event_type or not channel:
            raise ValidationError("Each preference requires event_type and channel.")
        if allowed_channels and channel not in allowed_channels:
            raise ValidationError(f"Channel {channel} is not enabled.")
        existing = (
            await session.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.event_type == event_type,
                    NotificationPreference.channel == channel,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                NotificationPreference(
                    user_id=user_id,
                    event_type=event_type,
                    channel=channel,
                    is_enabled=bool(item.get("is_enabled", True)),
                )
            )
        else:
            existing.is_enabled = bool(item.get("is_enabled", True))
            existing.updated_at = utcnow()
    await session.flush()
    return await list_preferences(session, user_id)


async def add_subscription(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    p256dh_key: str,
    auth_key: str,
    user_agent: str | None,
) -> PushSubscription:
    existing = (
        await session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.user_id = user_id
        existing.p256dh_key = p256dh_key
        existing.auth_key = auth_key
        existing.is_active = True
        existing.failure_count = 0
        existing.user_agent = user_agent
        await session.flush()
        return existing
    row = PushSubscription(
        user_id=user_id,
        endpoint=endpoint,
        p256dh_key=p256dh_key,
        auth_key=auth_key,
        user_agent=user_agent,
    )
    session.add(row)
    await session.flush()
    return row


async def remove_subscription(session: AsyncSession, *, user_id: uuid.UUID, subscription_id: uuid.UUID) -> None:
    row = await session.get(PushSubscription, subscription_id)
    if row is None or row.user_id != user_id:
        raise NotFound("Push subscription not found.")
    row.is_active = False
    await session.flush()