"""Notification tables (docs/02_DATABASE.md section 15)."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bool_false, bool_true, created_at_col, uuid_pk

CHANNELS = "('IN_APP','WEB_PUSH','EMAIL','SMS','WHATSAPP')"
DELIVERY_STATUS = "('PENDING','SENT','FAILED','SKIPPED','NOT_CONFIGURED')"
PRIORITY = "('LOW','NORMAL','HIGH')"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = uuid_pk()
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    data: Mapped[Any | None] = mapped_column(JSONB)
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'NORMAL'"))
    is_read: Mapped[bool] = bool_false()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"priority IN {PRIORITY}", name="ck_notifications_priority"),
        CheckConstraint("is_read = (read_at IS NOT NULL)", name="ck_notifications_read_shape"),
        Index("ix_notifications_recipient_read_created", "recipient_user_id", "is_read", text("created_at DESC")),
        Index("ix_notifications_recipient_created", "recipient_user_id", text("created_at DESC")),
        Index("ix_notifications_entity", "entity_type", "entity_id"),
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = uuid_pk()
    notification_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("notifications.id"), nullable=False
    )
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_notification_deliveries_notification_channel"),
        CheckConstraint(f"channel IN {CHANNELS}", name="ck_notification_deliveries_channel"),
        CheckConstraint(f"status IN {DELIVERY_STATUS}", name="ck_notification_deliveries_status"),
        CheckConstraint("attempts >= 0", name="ck_notification_deliveries_attempts"),
        Index("ix_notification_deliveries_retry", "status", "next_retry_at"),
    )


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = bool_true()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("user_id", "event_type", "channel", name="uq_notification_preferences_user_event_channel"),
        CheckConstraint(f"channel IN {CHANNELS}", name="ck_notification_preferences_channel"),
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh_key: Mapped[str] = mapped_column(Text, nullable=False)
    auth_key: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = bool_true()
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = created_at_col()
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "endpoint", name="uq_push_subscriptions_user_endpoint"),
        CheckConstraint("failure_count >= 0", name="ck_push_subscriptions_failure_count"),
    )