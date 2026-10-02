"""Orders service: broadcasting, atomic claiming and lifecycle.

The claim is decided by the database (docs/01_ARCHITECTURE.md section 21.1): a
conditional UPDATE plus a partial unique index guarantee exactly one winner.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ClaimAlreadyTaken, Conflict, NotFound, RuleViolation, ValidationError
from app.core.timeutil import utcnow
from app.modules.directory.models import Employee
from app.modules.orders.models import (
    Order,
    OrderAttachment,
    OrderBroadcast,
    OrderClaim,
    OrderStatusHistory,
)
from app.modules.settings.service import SettingsView

TERMINAL_STATUSES = frozenset({"DELIVERED", "CANCELLED", "FAILED"})
ASSIGNED_STATUSES = frozenset({"CLAIMED", "PACKING", "PACKED", "READY_FOR_DELIVERY", "OUT_FOR_DELIVERY"})
POD_PURPOSES = frozenset({"PACKING_PROOF", "DELIVERY_PROOF", "CUSTOMER_CONFIRMATION"})

TRANSITIONS: dict[str, tuple[str, ...]] = {
    "BROADCASTED": ("CLAIMED", "CANCELLED"),
    "CLAIMED": ("PACKING", "FAILED", "CANCELLED", "REASSIGNED"),
    "PACKING": ("PACKED", "FAILED", "CANCELLED", "REASSIGNED"),
    "PACKED": ("READY_FOR_DELIVERY", "FAILED", "CANCELLED", "REASSIGNED"),
    "READY_FOR_DELIVERY": ("OUT_FOR_DELIVERY", "FAILED", "CANCELLED", "REASSIGNED"),
    "OUT_FOR_DELIVERY": ("DELIVERED", "FAILED"),
    "REASSIGNED": ("BROADCASTED",),
}


def _money(value: Any) -> str:
    return f"{Decimal(str(value)):.2f}"


def serialize_order(order: Order, *, allowed_transitions: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "id": order.id,
        "order_code": order.order_code,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "delivery_address": order.delivery_address,
        "delivery_notes": order.delivery_notes,
        "item_summary": order.item_summary,
        "item_count": order.item_count,
        "order_amount": _money(order.order_amount),
        "currency": order.currency,
        "payment_mode": order.payment_mode,
        "status": order.status,
        "current_assignee_id": order.current_assignee_id,
        "claimed_at": order.claimed_at,
        "claim_expires_at": order.claim_expires_at,
        "broadcast_at": order.broadcast_at,
        "reassigned_at": order.reassigned_at,
        "reassign_count": order.reassign_count,
        "pod_required": order.pod_required,
        "packed_at": order.packed_at,
        "ready_at": order.ready_at,
        "dispatched_at": order.dispatched_at,
        "delivered_at": order.delivered_at,
        "cancelled_at": order.cancelled_at,
        "cancel_reason": order.cancel_reason,
        "failed_at": order.failed_at,
        "failure_reason": order.failure_reason,
        "notes": order.notes,
        "version": order.version,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }
    if allowed_transitions is not None:
        payload["allowed_transitions"] = allowed_transitions
    return payload


def allowed_transitions_for(
    order: Order, *, is_holder: bool, can_claim: bool, can_cancel: bool, can_reassign: bool, can_any: bool
) -> list[str]:
    options = TRANSITIONS.get(order.status, ())
    result: list[str] = []
    for target in options:
        if target == "CLAIMED":
            if order.status == "BROADCASTED" and can_claim:
                result.append(target)
        elif target == "CANCELLED":
            if can_cancel or can_any:
                result.append(target)
        elif target == "REASSIGNED":
            if can_reassign:
                result.append(target)
        elif target == "BROADCASTED":
            if can_reassign:
                result.append(target)
        elif is_holder or can_any:
            result.append(target)
    return result


async def get_order(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFound("Order not found.")
    return order


async def count_active_claims(session: AsyncSession, employee_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(OrderClaim)
                .where(OrderClaim.employee_id == employee_id, OrderClaim.status == "ACTIVE")
            )
        ).scalar_one()
    )


async def active_claim_for_order(session: AsyncSession, order_id: uuid.UUID) -> OrderClaim | None:
    return (
        await session.execute(
            select(OrderClaim).where(OrderClaim.order_id == order_id, OrderClaim.status == "ACTIVE")
        )
    ).scalar_one_or_none()


async def active_broadcast(session: AsyncSession, order_id: uuid.UUID) -> OrderBroadcast | None:
    return (
        await session.execute(
            select(OrderBroadcast)
            .where(OrderBroadcast.order_id == order_id, OrderBroadcast.is_active.is_(True))
            .order_by(OrderBroadcast.round_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def audience_allows(broadcast: OrderBroadcast | None, employee: Employee) -> bool:
    if broadcast is None:
        return False
    scope = broadcast.audience_scope or "ALL_ACTIVE_EMPLOYEES"
    if scope == "ALL_ACTIVE_EMPLOYEES":
        return employee.employment_status == "ACTIVE"
    if scope == "DEPARTMENTS":
        payload = broadcast.audience_payload or {}
        departments = payload.get("departments") or payload.get("department") or []
        if isinstance(departments, str):
            departments = [departments]
        return employee.department in departments
    if scope == "EMPLOYEES":
        payload = broadcast.audience_payload or {}
        targets = payload.get("employee_ids") or []
        return str(employee.id) in {str(item) for item in targets}
    return False


async def create_order(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    order_code: str | None,
    customer_name: str,
    customer_phone: str | None,
    delivery_address: str | None,
    delivery_notes: str | None,
    item_summary: str | None,
    item_count: int | None,
    order_amount: Decimal,
    currency: str,
    payment_mode: str | None,
    notes: str | None,
    broadcast: dict[str, Any] | None,
    settings: SettingsView,
) -> Order:
    code = order_code or _generate_order_code()
    existing = (
        await session.execute(select(Order.id).where(Order.order_code == code))
    ).scalar_one_or_none()
    if existing:
        from app.core.errors import DuplicateConflict

        raise DuplicateConflict(f"Order code {code} already exists.")
    order = Order(
        order_code=code,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        delivery_notes=delivery_notes,
        item_summary=item_summary,
        item_count=item_count,
        order_amount=order_amount,
        currency=currency,
        payment_mode=payment_mode,
        status="BROADCASTED" if broadcast else "BROADCASTED",
        created_by=actor_user_id,
        notes=notes,
        pod_required=settings.bool_("orders.pod_required"),
    )
    session.add(order)
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=None,
        to_status=order.status,
        changed_by=actor_user_id,
        reason="Order registered.",
    )
    if broadcast is not None:
        await broadcast_order(
            session,
            order=order,
            actor_user_id=actor_user_id,
            audience_scope=broadcast.get("audience_scope"),
            audience_payload=broadcast.get("audience_payload"),
            expires_at=None,
            settings=settings,
        )
    return order


def _generate_order_code() -> str:
    now = utcnow()
    return f"ORD-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


async def _write_history(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    from_status: str | None,
    to_status: str,
    changed_by: uuid.UUID | None,
    employee_id: uuid.UUID | None = None,
    reason: str | None = None,
    actor_type: str = "USER",
    metadata: dict[str, Any] | None = None,
) -> OrderStatusHistory:
    row = OrderStatusHistory(
        order_id=order_id,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        actor_type=actor_type,
        employee_id=employee_id,
        reason=reason,
        meta=metadata,
    )
    session.add(row)
    await session.flush()
    return row


async def broadcast_order(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    audience_scope: str | None,
    audience_payload: dict[str, Any] | None,
    expires_at: datetime | None,
    settings: SettingsView,
) -> OrderBroadcast:
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("A terminal order cannot be broadcast.", rule_code="ORDER_TERMINAL")
    if order.status in ASSIGNED_STATUSES:
        raise RuleViolation(
            "This order already has an active claim.", rule_code="ORDER_ALREADY_CLAIMED"
        )
    last_round = (
        await session.execute(
            select(func.coalesce(func.max(OrderBroadcast.round_no), 0)).where(
                OrderBroadcast.order_id == order.id
            )
        )
    ).scalar_one()
    await session.execute(
        update(OrderBroadcast)
        .where(OrderBroadcast.order_id == order.id, OrderBroadcast.is_active.is_(True))
        .values(is_active=False)
    )
    now = utcnow()
    if expires_at is None and settings.int_("orders.claim_timeout_minutes") > 0:
        expires_at = now + timedelta(days=7)
    row = OrderBroadcast(
        order_id=order.id,
        round_no=int(last_round) + 1,
        broadcast_by=actor_user_id,
        broadcast_at=now,
        audience_scope=audience_scope or settings.str_("orders.broadcast_audience"),
        audience_payload=audience_payload,
        expires_at=expires_at,
        is_active=True,
    )
    session.add(row)
    order.status = "BROADCASTED"
    order.broadcast_at = now
    order.current_assignee_id = None
    order.updated_at = now
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status="REASSIGNED" if order.reassign_count else None,
        to_status="BROADCASTED",
        changed_by=actor_user_id,
        reason="Broadcast to employees.",
    )
    return row

async def claim_order(
    session: AsyncSession,
    *,
    order_id: uuid.UUID,
    employee: Employee,
    actor_user_id: uuid.UUID,
    settings: SettingsView,
) -> tuple[Order, OrderClaim]:
    if employee.employment_status != "ACTIVE":
        raise RuleViolation("Only active employees may claim orders.", rule_code="NOT_ELIGIBLE")
    max_claims = settings.int_("orders.max_active_claims_per_employee")
    if max_claims > 0:
        active = await count_active_claims(session, employee.id)
        if active >= max_claims:
            raise RuleViolation(
                "You already hold the maximum number of active orders.",
                rule_code="MAX_ACTIVE_CLAIMS",
            )
    if settings.bool_("orders.claim_requires_active_attendance"):
        from app.modules.attendance import service as attendance_service

        if await attendance_service.find_open_session(session, employee.id) is None:
            raise RuleViolation(
                "You must be checked in to claim an order.",
                rule_code="ATTENDANCE_REQUIRED",
            )
    order = await get_order(session, order_id)
    broadcast = await active_broadcast(session, order_id)
    if not audience_allows(broadcast, employee):
        raise NotFound("Order not found.")
    now = utcnow()
    expires_at = None
    if settings.bool_("orders.auto_release_on_timeout"):
        timeout = settings.int_("orders.claim_timeout_minutes")
        if timeout > 0:
            expires_at = now + timedelta(minutes=timeout)
    result = await session.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == "BROADCASTED",
            Order.current_assignee_id.is_(None),
        )
        .values(
            status="CLAIMED",
            current_assignee_id=employee.id,
            claimed_at=now,
            claim_expires_at=expires_at,
            updated_at=now,
        )
    )
    if not result.rowcount:
        current = await session.get(Order, order_id, populate_existing=True)
        existing_claim = await active_claim_for_order(session, order_id)
        await session.rollback()
        raise ClaimAlreadyTaken(
            "Another employee has already claimed this order.",
            extra={
                "order_id": str(order_id),
                "status": current.status if current else None,
                "current_assignee_id": str(current.current_assignee_id)
                if current and current.current_assignee_id
                else None,
                "claimed_at": (existing_claim.claimed_at or current.claimed_at)
                if existing_claim or current
                else None,
            },
        )
    claim = OrderClaim(
        order_id=order_id,
        employee_id=employee.id,
        order_broadcast_id=broadcast.id if broadcast else None,
        status="ACTIVE",
        claimed_at=now,
        claim_expires_at=expires_at,
    )
    session.add(claim)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ClaimAlreadyTaken("Another employee has already claimed this order.") from exc
    if broadcast is not None:
        broadcast.is_active = False
    await _write_history(
        session,
        order_id=order_id,
        from_status="BROADCASTED",
        to_status="CLAIMED",
        changed_by=actor_user_id,
        employee_id=employee.id,
        reason="Claimed by employee.",
    )
    order = await session.get(Order, order_id, populate_existing=True)
    return order, claim


async def release_claim(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    reason: str,
    end_reason: str = "RELEASED_BY_EMPLOYEE",
    rebroadcast: bool = True,
    settings: SettingsView,
) -> Order:
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("A terminal order cannot be released.", rule_code="ORDER_TERMINAL")
    claim = await active_claim_for_order(session, order.id)
    now = utcnow()
    if claim is not None:
        claim.status = end_reason if end_reason in {
            "DELIVERED",
            "FAILED",
            "RELEASED_BY_EMPLOYEE",
            "REVOKED_BY_ADMIN",
            "EXPIRED",
            "REASSIGNED",
            "CANCELLED",
        } else "RELEASED_BY_EMPLOYEE"
        claim.ended_at = now
        claim.ended_by = actor_user_id
        claim.end_reason = reason
    previous = order.status
    order.current_assignee_id = None
    order.claimed_at = None
    order.claim_expires_at = None
    order.status = "BROADCASTED" if rebroadcast else "REASSIGNED"
    order.updated_at = now
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=previous,
        to_status=order.status,
        changed_by=actor_user_id,
        employee_id=employee_id,
        reason=reason,
    )
    if rebroadcast:
        active = await active_broadcast(session, order.id)
        if active is None or not active.is_active:
            await broadcast_order(
                session,
                order=order,
                actor_user_id=actor_user_id,
                audience_scope=None,
                audience_payload=None,
                expires_at=None,
                settings=settings,
            )
    return order


async def transition_status(
    session: AsyncSession,
    *,
    order: Order,
    to_status: str,
    actor_user_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    reason: str | None,
    note: str | None,
    evidence: dict[str, Any] | None,
    proof_file_ids: list[uuid.UUID],
    is_holder: bool,
    can_any: bool,
    settings: SettingsView,
) -> Order:
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("This order has reached a terminal state.", rule_code="ORDER_TERMINAL")
    allowed = TRANSITIONS.get(order.status, ())
    if to_status not in allowed:
        raise RuleViolation(
            f"Cannot move an order from {order.status} to {to_status}.",
            rule_code="INVALID_ORDER_TRANSITION",
        )
    if to_status != "CANCELLED" and not (is_holder or can_any):
        raise Conflict("You do not hold this order.")
    if to_status == "DELIVERED":
        await _assert_pod(session, order, proof_file_ids, settings)
    if to_status == "FAILED" and settings.bool_("orders.failure_requires_reason") and not reason:
        raise RuleViolation("A failure reason is required.", rule_code="FAILURE_REASON_REQUIRED")
    if to_status == "PACKED" and settings.bool_("orders.packing_proof_required"):
        if not proof_file_ids:
            raise RuleViolation(
                "Packing proof is required before marking an order packed.",
                rule_code="PACKING_PROOF_REQUIRED",
            )
    now = utcnow()
    previous = order.status
    order.status = to_status
    order.updated_at = now
    if to_status == "PACKED":
        order.packed_at = now
    elif to_status == "READY_FOR_DELIVERY":
        order.ready_at = now
    elif to_status == "OUT_FOR_DELIVERY":
        order.dispatched_at = now
    elif to_status == "DELIVERED":
        order.delivered_at = now
        claim = await active_claim_for_order(session, order.id)
        if claim is not None:
            claim.status = "DELIVERED"
            claim.ended_at = now
            claim.ended_by = actor_user_id
            claim.end_reason = "DELIVERED"
        order.claim_expires_at = None
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=previous,
        to_status=to_status,
        changed_by=actor_user_id,
        employee_id=employee_id,
        reason=reason or note,
        metadata={"evidence": evidence} if evidence else None,
    )
    for file_id in proof_file_ids:
        await add_attachment(
            session,
            order=order,
            actor_user_id=actor_user_id,
            employee_id=employee_id,
            file_id=file_id,
            purpose=_purpose_for(to_status),
            note=note,
            evidence=evidence,
            settings=settings,
        )
    return order


def _purpose_for(status: str) -> str:
    if status == "DELIVERED":
        return "DELIVERY_PROOF"
    if status in {"PACKED", "READY_FOR_DELIVERY"}:
        return "PACKING_PROOF"
    return "PACKING_PROOF"


async def _assert_pod(
    session: AsyncSession,
    order: Order,
    proof_file_ids: list[uuid.UUID],
    settings: SettingsView,
) -> None:
    if not settings.bool_("orders.pod_required"):
        return
    attachments = list(
        (
            await session.execute(
                select(OrderAttachment).where(OrderAttachment.order_id == order.id)
            )
        ).scalars().all()
    )
    has_photo = bool(proof_file_ids) or any(
        row.purpose == "DELIVERY_PROOF" for row in attachments
    )
    if settings.bool_("orders.pod_requires_photo") and not has_photo:
        raise RuleViolation(
            "Proof of delivery (a photo) is required.", rule_code="POD_REQUIRED"
        )
    if settings.bool_("orders.pod_requires_customer_confirmation"):
        if not any(row.customer_confirmed_at is not None for row in attachments):
            raise RuleViolation(
                "Customer confirmation is required for delivery.", rule_code="POD_CONFIRMATION_REQUIRED"
            )
    if settings.bool_("orders.pod_requires_location"):
        if not any(row.latitude is not None for row in attachments):
            raise RuleViolation(
                "A delivery location is required for proof of delivery.",
                rule_code="POD_LOCATION_REQUIRED",
            )


async def add_attachment(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    file_id: uuid.UUID,
    purpose: str,
    note: str | None,
    evidence: dict[str, Any] | None,
    settings: SettingsView,
) -> OrderAttachment:
    if purpose not in POD_PURPOSES:
        raise ValidationError("Unsupported attachment purpose for orders.")
    from app.modules.files import service as file_service

    await file_service.assert_exists(session, file_id)
    now = utcnow()
    row = OrderAttachment(
        order_id=order.id,
        file_id=file_id,
        purpose=purpose,
        uploaded_by=actor_user_id,
        note=note,
        latitude=Decimal(str(evidence["latitude"])) if evidence and evidence.get("latitude") is not None else None,
        longitude=Decimal(str(evidence["longitude"])) if evidence and evidence.get("longitude") is not None else None,
        accuracy_meters=Decimal(str(evidence["accuracy_meters"]))
        if evidence and evidence.get("accuracy_meters") is not None
        else None,
    )
    session.add(row)
    await session.flush()
    return row


async def reassign_order(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    new_assignee_employee_id: uuid.UUID | None,
    reason: str,
    settings: SettingsView,
) -> tuple[Order, OrderClaim | None]:
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("A terminal order cannot be reassigned.", rule_code="ORDER_TERMINAL")
    if settings.bool_("orders.reassignment_requires_reason") and not reason:
        raise RuleViolation("A reassignment reason is required.", rule_code="REASON_REQUIRED")
    max_reassign = settings.int_("orders.max_reassignments")
    if max_reassign and int(order.reassign_count or 0) >= max_reassign:
        raise RuleViolation(
            "The maximum number of reassignments has been reached.",
            rule_code="MAX_REASSIGNMENTS",
        )
    previous_assignee = order.current_assignee_id
    claim = await active_claim_for_order(session, order.id)
    now = utcnow()
    if claim is not None:
        claim.status = "REASSIGNED"
        claim.ended_at = now
        claim.ended_by = actor_user_id
        claim.end_reason = reason
    previous = order.status
    order.current_assignee_id = None
    order.claimed_at = None
    order.claim_expires_at = None
    order.reassign_count = int(order.reassign_count or 0) + 1
    order.reassigned_at = now
    order.status = "REASSIGNED"
    order.updated_at = now
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=previous,
        to_status="REASSIGNED",
        changed_by=actor_user_id,
        employee_id=previous_assignee,
        reason=reason,
    )
    new_claim: OrderClaim | None = None
    if new_assignee_employee_id is not None:
        target = await session.get(Employee, new_assignee_employee_id)
        if target is None or target.employment_status != "ACTIVE":
            raise NotFound("The target employee is not active.")
        await session.execute(
            update(Order)
            .where(Order.id == order.id)
            .values(
                status="CLAIMED",
                current_assignee_id=target.id,
                claimed_at=now,
                updated_at=now,
            )
        )
        new_claim = OrderClaim(
            order_id=order.id,
            employee_id=target.id,
            order_broadcast_id=None,
            status="ACTIVE",
            claimed_at=now,
        )
        session.add(new_claim)
        await session.flush()
        await _write_history(
            session,
            order_id=order.id,
            from_status="REASSIGNED",
            to_status="CLAIMED",
            changed_by=actor_user_id,
            employee_id=target.id,
            reason="Assigned by administrator.",
        )
        order = await session.get(Order, order.id, populate_existing=True)
    elif settings.bool_("orders.allow_rebroadcast_after_release"):
        await broadcast_order(
            session,
            order=order,
            actor_user_id=actor_user_id,
            audience_scope=None,
            audience_payload=None,
            expires_at=None,
            settings=settings,
        )
    return order, new_claim


async def cancel_order(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    reason: str,
    cancellation_code: str | None,
    settings: SettingsView,
) -> Order:
    allowed = settings.json_("orders.cancel_allowed_statuses") or []
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("This order is already terminal.", rule_code="ORDER_TERMINAL")
    if allowed and order.status not in allowed:
        raise RuleViolation(
            f"An order in status {order.status} cannot be cancelled.",
            rule_code="CANCEL_NOT_ALLOWED",
        )
    claim = await active_claim_for_order(session, order.id)
    now = utcnow()
    if claim is not None:
        claim.status = "CANCELLED"
        claim.ended_at = now
        claim.ended_by = actor_user_id
        claim.end_reason = reason
    previous = order.status
    order.status = "CANCELLED"
    order.cancelled_at = now
    order.cancel_reason = reason
    order.current_assignee_id = None
    order.claim_expires_at = None
    order.updated_at = now
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=previous,
        to_status="CANCELLED",
        changed_by=actor_user_id,
        reason=reason,
        metadata={"cancellation_code": cancellation_code} if cancellation_code else None,
    )
    return order


async def fail_order(
    session: AsyncSession,
    *,
    order: Order,
    actor_user_id: uuid.UUID,
    employee_id: uuid.UUID | None,
    failure_reason: str,
    reason_code: str | None,
    settings: SettingsView,
) -> Order:
    if order.status in TERMINAL_STATUSES:
        raise RuleViolation("This order is already terminal.", rule_code="ORDER_TERMINAL")
    if settings.bool_("orders.failure_requires_reason") and not failure_reason:
        raise RuleViolation("A failure reason is required.", rule_code="FAILURE_REASON_REQUIRED")
    claim = await active_claim_for_order(session, order.id)
    now = utcnow()
    if claim is not None:
        claim.status = "FAILED"
        claim.ended_at = now
        claim.ended_by = actor_user_id
        claim.end_reason = failure_reason
    previous = order.status
    order.status = "FAILED"
    order.failed_at = now
    order.failure_reason = failure_reason
    order.current_assignee_id = None
    order.claim_expires_at = None
    order.updated_at = now
    await session.flush()
    await _write_history(
        session,
        order_id=order.id,
        from_status=previous,
        to_status="FAILED",
        changed_by=actor_user_id,
        employee_id=employee_id,
        reason=failure_reason,
        metadata={"reason_code": reason_code} if reason_code else None,
    )
    return order


async def history(session: AsyncSession, order_id: uuid.UUID) -> list[OrderStatusHistory]:
    return list(
        (
            await session.execute(
                select(OrderStatusHistory)
                .where(OrderStatusHistory.order_id == order_id)
                .order_by(OrderStatusHistory.changed_at, OrderStatusHistory.id)
            )
        ).scalars().all()
    )


def serialize_history(row: OrderStatusHistory) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "from_status": row.from_status,
        "to_status": row.to_status,
        "changed_by": row.changed_by,
        "actor_type": row.actor_type,
        "employee_id": row.employee_id,
        "reason": row.reason,
        "metadata": row.meta,
        "changed_at": row.changed_at,
    }


def serialize_claim(row: OrderClaim) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "employee_id": row.employee_id,
        "status": row.status,
        "claimed_at": row.claimed_at,
        "claim_expires_at": row.claim_expires_at,
        "ended_at": row.ended_at,
        "end_reason": row.end_reason,
    }


def serialize_attachment(row: OrderAttachment) -> dict[str, Any]:
    return {
        "id": row.id,
        "order_id": row.order_id,
        "file_id": row.file_id,
        "purpose": row.purpose,
        "uploaded_by": row.uploaded_by,
        "uploaded_at": row.uploaded_at,
        "note": row.note,
        "latitude": str(row.latitude) if row.latitude is not None else None,
        "longitude": str(row.longitude) if row.longitude is not None else None,
        "accuracy_meters": str(row.accuracy_meters) if row.accuracy_meters is not None else None,
        "customer_confirmed_at": row.customer_confirmed_at,
        "customer_confirmation_method": row.customer_confirmation_method,
    }


async def list_attachments(session: AsyncSession, order_id: uuid.UUID) -> list[OrderAttachment]:
    return list(
        (
            await session.execute(
                select(OrderAttachment)
                .where(OrderAttachment.order_id == order_id)
                .order_by(OrderAttachment.uploaded_at.asc())
            )
        ).scalars().all()
    )


async def list_orders(
    session: AsyncSession,
    *,
    status: str | None = None,
    assignee_employee_id: uuid.UUID | None = None,
    unassigned: bool | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Order], int]:
    conditions = []
    if status:
        conditions.append(Order.status == status)
    if assignee_employee_id:
        conditions.append(Order.current_assignee_id == assignee_employee_id)
    if unassigned:
        conditions.append(Order.current_assignee_id.is_(None))
    if from_date:
        conditions.append(func.date(Order.created_at) >= from_date)
    if to_date:
        conditions.append(func.date(Order.created_at) <= to_date)
    if q:
        pattern = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Order.order_code).like(pattern),
                func.lower(Order.customer_name).like(pattern),
            )
        )
    stmt = select(Order).order_by(Order.created_at.desc())
    count_stmt = select(func.count()).select_from(Order)
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def available_orders(
    session: AsyncSession,
    *,
    employee: Employee,
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[Order], int]:
    stmt = (
        select(Order)
        .join(OrderBroadcast, OrderBroadcast.order_id == Order.id)
        .where(
            Order.status == "BROADCASTED",
            Order.current_assignee_id.is_(None),
            OrderBroadcast.is_active.is_(True),
            or_(
                OrderBroadcast.audience_scope == "ALL_ACTIVE_EMPLOYEES",
                and_(
                    OrderBroadcast.audience_scope == "DEPARTMENTS",
                    OrderBroadcast.audience_payload["departments"].contains([employee.department]),
                ),
                and_(
                    OrderBroadcast.audience_scope == "EMPLOYEES",
                    OrderBroadcast.audience_payload["employee_ids"].contains([str(employee.id)]),
                ),
            ),
        )
        .order_by(OrderBroadcast.broadcast_at.asc())
    )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list((await session.execute(stmt.offset(offset).limit(limit))).scalars().all())
    return rows, total


async def expire_claims(session: AsyncSession, settings: SettingsView) -> int:
    """Job: auto-release claims past claim_expires_at."""
    if not settings.bool_("orders.auto_release_on_timeout"):
        return 0
    now = utcnow()
    rows = list(
        (
            await session.execute(
                select(OrderClaim)
                .where(OrderClaim.status == "ACTIVE", OrderClaim.claim_expires_at <= now)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
    )
    handled = 0
    for claim in rows:
        order = await get_order(session, claim.order_id)
        if order.status in TERMINAL_STATUSES:
            continue
        claim.status = "EXPIRED"
        claim.ended_at = now
        claim.end_reason = "Claim timeout"
        previous = order.status
        order.status = "BROADCASTED"
        order.current_assignee_id = None
        order.claimed_at = None
        order.claim_expires_at = None
        order.updated_at = now
        await session.flush()
        await _write_history(
            session,
            order_id=order.id,
            from_status=previous,
            to_status="BROADCASTED",
            changed_by=None,
            employee_id=claim.employee_id,
            reason="Claim timed out.",
            actor_type="SYSTEM",
        )
        handled += 1
    return handled