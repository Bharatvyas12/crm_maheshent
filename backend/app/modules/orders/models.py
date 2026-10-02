"""Order tables (docs/02_DATABASE.md section 11)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.mixins import bigint_pk, bool_false, bool_true, created_at_col, money_col, uuid_pk, version_col

ORDER_STATUS = (
    "('BROADCASTED','CLAIMED','PACKING','PACKED','READY_FOR_DELIVERY','OUT_FOR_DELIVERY',"
    "'DELIVERED','CANCELLED','FAILED','REASSIGNED')"
)
ASSIGNED_STATUSES = "('CLAIMED','PACKING','PACKED','READY_FOR_DELIVERY','OUT_FOR_DELIVERY','DELIVERED')"
UNASSIGNED_STATUSES = "('BROADCASTED','REASSIGNED')"
PAYMENT_MODES = "('PREPAID','COD','OTHER')"
AUDIENCE_SCOPE = "('ALL_ACTIVE_EMPLOYEES','ROLE','EXPLICIT')"
CLAIM_STATUS = "('ACTIVE','COMPLETED','RELEASED','REVOKED','EXPIRED')"
END_REASON = (
    "('DELIVERED','FAILED','RELEASED_BY_EMPLOYEE','REVOKED_BY_ADMIN','EXPIRED','REASSIGNED','CANCELLED')"
)
ATTACHMENT_PURPOSE = "('PACKING_PROOF','DELIVERY_PROOF','CUSTOMER_CONFIRMATION','OTHER')"
CONFIRMATION_METHOD = "('SIGNATURE','OTP','VERBAL','PHOTO','APP')"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    customer_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(Text)
    delivery_address: Mapped[str | None] = mapped_column(Text)
    delivery_notes: Mapped[str | None] = mapped_column(Text)
    item_summary: Mapped[str | None] = mapped_column(Text)
    item_count: Mapped[int | None] = mapped_column(Integer)
    order_amount: Mapped[Decimal] = money_col(default="0")
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    payment_mode: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'BROADCASTED'"))
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    broadcast_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id")
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    packed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    reassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reassign_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    pod_required: Mapped[bool] = bool_true()
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = version_col()
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint(f"status IN {ORDER_STATUS}", name="ck_orders_status"),
        CheckConstraint(f"payment_mode IS NULL OR payment_mode IN {PAYMENT_MODES}", name="ck_orders_payment_mode"),
        CheckConstraint("item_count IS NULL OR item_count >= 0", name="ck_orders_item_count"),
        CheckConstraint("order_amount >= 0", name="ck_orders_amount"),
        CheckConstraint("char_length(order_code) BETWEEN 3 AND 40", name="ck_orders_code_length"),
        CheckConstraint(
            "(status IN " + ASSIGNED_STATUSES + " AND current_assignee_id IS NOT NULL)"
            " OR (status IN " + UNASSIGNED_STATUSES + " AND current_assignee_id IS NULL)"
            " OR status IN ('CANCELLED','FAILED')",
            name="ck_orders_assignee_presence",
        ),
        CheckConstraint("status <> 'DELIVERED' OR delivered_at IS NOT NULL", name="ck_orders_delivered_timestamp"),
        CheckConstraint("status <> 'CANCELLED' OR cancel_reason IS NOT NULL", name="ck_orders_cancelled_reason"),
        CheckConstraint("reassign_count >= 0", name="ck_orders_reassign_count"),
        Index("ix_orders_status_broadcast", "status", "broadcast_at"),
        Index("ix_orders_assignee_status", "current_assignee_id", "status"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_claim_expires_at", "claim_expires_at", postgresql_where=text("claim_expires_at IS NOT NULL")),
    )


class OrderBroadcast(Base):
    __tablename__ = "order_broadcasts"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    round_no: Mapped[int] = mapped_column(Integer, nullable=False)
    broadcast_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    broadcast_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    audience_scope: Mapped[str] = mapped_column(Text, nullable=False)
    audience_payload: Mapped[Any | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = bool_true()

    __table_args__ = (
        UniqueConstraint("order_id", "round_no", name="uq_order_broadcasts_order_round"),
        CheckConstraint(f"audience_scope IN {AUDIENCE_SCOPE}", name="ck_order_broadcasts_scope"),
        CheckConstraint("round_no >= 1", name="ck_order_broadcasts_round"),
        Index(
            "uq_order_broadcasts_active_order",
            "order_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class OrderClaim(Base):
    __tablename__ = "order_claims"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("employees.id"), nullable=False
    )
    order_broadcast_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("order_broadcasts.id")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ACTIVE'"))
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    end_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint(f"status IN {CLAIM_STATUS}", name="ck_order_claims_status"),
        CheckConstraint(f"end_reason IS NULL OR end_reason IN {END_REASON}", name="ck_order_claims_end_reason"),
        CheckConstraint("status = 'ACTIVE' OR ended_at IS NOT NULL", name="ck_order_claims_ended"),
        Index(
            "uq_order_claims_active_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_order_claims_active_employee",
            "employee_id",
            text("claimed_at DESC"),
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_order_claims_expiry", "status", "claim_expires_at"),
    )


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = bigint_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    actor_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'USER'"))
    employee_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("employees.id"))
    reason: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[Any | None] = mapped_column("metadata", JSONB)
    changed_at: Mapped[datetime] = created_at_col()

    __table_args__ = (
        CheckConstraint("actor_type IN ('USER','SYSTEM')", name="ck_order_status_history_actor_type"),
        Index("ix_order_status_history_order_changed", "order_id", "changed_at"),
        Index("ix_order_status_history_to_status_changed", "to_status", "changed_at"),
    )


class OrderAttachment(Base):
    __tablename__ = "order_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id"), nullable=False, unique=True
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    note: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    accuracy_meters: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    customer_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_confirmation_method: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"purpose IN {ATTACHMENT_PURPOSE}", name="ck_order_attachments_purpose"),
        CheckConstraint(
            f"customer_confirmation_method IS NULL OR customer_confirmation_method IN {CONFIRMATION_METHOD}",
            name="ck_order_attachments_confirmation_method",
        ),
        Index("ix_order_attachments_order_purpose", "order_id", "purpose"),
    )