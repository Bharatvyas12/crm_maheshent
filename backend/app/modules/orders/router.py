"""Orders endpoints (docs/03_API_CONTRACT.md section 9)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.context import Ctx, parse_date, require
from app.api.idempotency import begin_idempotency, finish_idempotency, replay_response
from app.core.errors import NotFound, PermissionDenied, RuleViolation, ValidationError
from app.core.money import quantize_money
from app.core.pagination import PageParams, page_params, paginated
from app.modules.directory import service as directory_service
from app.modules.orders import service

router = APIRouter(tags=["orders"])

PAYMENT_MODES = {"PREPAID", "COD", "OTHER", "CASH", "CARD", "UPI"}
PAYMENT_MODE_MAP = {
    "CASH": "COD",
    "COD": "COD",
    "CARD": "PREPAID",
    "UPI": "PREPAID",
    "PREPAID": "PREPAID",
    "OTHER": "OTHER",
}


class BroadcastInput(BaseModel):
    audience_scope: str | None = None
    audience_payload: dict | None = None


class OrderCreateRequest(BaseModel):
    order_code: str | None = Field(default=None, max_length=64)
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    delivery_address: str | None = Field(default=None, max_length=1000)
    delivery_notes: str | None = Field(default=None, max_length=1000)
    item_summary: str | None = Field(default=None, max_length=2000)
    item_count: int | None = Field(default=None, ge=0)
    order_amount: Decimal | None = Field(default=Decimal("0.00"))
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    payment_mode: str | None = None
    notes: str | None = Field(default=None, max_length=2000)
    proof_file_ids: list[uuid.UUID] = Field(default_factory=list)
    broadcast: BroadcastInput | None = None


class OrderUpdateRequest(BaseModel):
    customer_name: str | None = Field(default=None, min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=40)
    delivery_address: str | None = Field(default=None, max_length=1000)
    delivery_notes: str | None = Field(default=None, max_length=1000)
    item_summary: str | None = Field(default=None, max_length=2000)
    item_count: int | None = Field(default=None, ge=0)
    order_amount: Decimal | None = None
    payment_mode: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BroadcastRequest(BaseModel):
    audience_scope: str | None = None
    audience_payload: dict | None = None
    expires_at: datetime | None = None


class ReleaseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class StatusRequest(BaseModel):
    to_status: str
    reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=1000)
    evidence: dict | None = None
    proof_file_ids: list[uuid.UUID] = Field(default_factory=list)


class ReassignRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    new_assignee_employee_id: uuid.UUID | None = None


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    cancellation_code: str | None = Field(default=None, max_length=64)


class FailRequest(BaseModel):
    failure_reason: str = Field(min_length=1, max_length=1000)
    reason_code: str | None = Field(default=None, max_length=64)


class AttachmentRequest(BaseModel):
    file_id: uuid.UUID
    purpose: str
    note: str | None = Field(default=None, max_length=1000)
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    accuracy_meters: Decimal | None = None
    customer_confirmed: bool = False
    customer_confirmation_method: str | None = None


def _transitions(ctx: Ctx, order) -> list[str]:
    is_holder = order.current_assignee_id == ctx.actor.employee_id
    return service.allowed_transitions_for(
        order,
        is_holder=is_holder,
        can_claim=ctx.actor.has("order.claim"),
        can_cancel=ctx.actor.has("order.cancel"),
        can_reassign=ctx.actor.has("order.reassign"),
        can_any=ctx.actor.has("order.update.status.any"),
    )


def _payload(ctx: Ctx, order) -> dict:
    return service.serialize_order(order, allowed_transitions=_transitions(ctx, order))


@router.get("/orders")
async def list_orders(
    status: str | None = Query(None),
    assignee_employee_id: uuid.UUID | None = Query(None),
    unassigned: bool | None = Query(None),
    from_: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    q: str | None = Query(None, max_length=100),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("order.read.all")),
) -> dict:
    rows, total = await service.list_orders(
        ctx.session,
        status=status,
        assignee_employee_id=assignee_employee_id,
        unassigned=unassigned,
        from_date=parse_date(from_, "from"),
        to_date=parse_date(to, "to"),
        q=q,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([_payload(ctx, row) for row in rows], total, params)


@router.post("/orders", status_code=201)
async def create_order(payload: OrderCreateRequest, ctx: Ctx = Depends(require("order.create"))) -> dict:
    if payload.payment_mode:
        raw_mode = payload.payment_mode.upper()
        if raw_mode not in PAYMENT_MODES:
            raise ValidationError(f"Unsupported payment mode: {payload.payment_mode}")
        payment_mode = PAYMENT_MODE_MAP.get(raw_mode, "OTHER")
    else:
        payment_mode = None
    amount = quantize_money(payload.order_amount) if payload.order_amount is not None else quantize_money(Decimal("0.00"))
    order = await service.create_order(
        ctx.session,
        actor_user_id=ctx.actor_user_id,
        order_code=payload.order_code,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        delivery_address=payload.delivery_address,
        delivery_notes=payload.delivery_notes,
        item_summary=payload.item_summary,
        item_count=payload.item_count,
        order_amount=amount,
        currency=(payload.currency or ctx.settings.currency()).upper(),
        payment_mode=payment_mode,
        notes=payload.notes,
        broadcast=payload.broadcast.model_dump() if payload.broadcast else None,
        settings=ctx.settings,
    )
    for fid in payload.proof_file_ids:
        await service.add_attachment(
            ctx.session,
            order=order,
            actor_user_id=ctx.actor_user_id,
            employee_id=ctx.actor.employee_id,
            file_id=fid,
            purpose="PACKING_PROOF",
            note="Uploaded during order registration",
            evidence=None,
            settings=ctx.settings,
        )
    await ctx.audit(
        category="ORDER",
        action="order.created",
        entity_type="order",
        entity_id=order.id,
        after={"order_code": order.order_code, "order_amount": str(order.order_amount)},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.broadcasted.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"order_code": order.order_code},
    )
    return _payload(ctx, order)


@router.get("/orders/available")
async def available_orders(
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("order.read.available")),
) -> dict:
    employee = await directory_service.get_employee(ctx.session, ctx.employee_id)
    rows, total = await service.available_orders(
        ctx.session, employee=employee, offset=params.offset, limit=params.page_size
    )
    return paginated(
        [service.serialize_order(row, allowed_transitions=["CLAIMED"] if ctx.actor.has("order.claim") else []) for row in rows],
        total,
        params,
    )


@router.get("/orders/mine")
async def my_orders(
    status: str | None = Query(None),
    include_history: bool = Query(False),
    params: PageParams = Depends(page_params),
    ctx: Ctx = Depends(require("order.read.self")),
) -> dict:
    statuses = [status] if status else (None if include_history else None)
    rows, total = await service.list_orders(
        ctx.session,
        status=statuses,
        assignee_employee_id=ctx.employee_id,
        offset=params.offset,
        limit=params.page_size,
    )
    return paginated([_payload(ctx, row) for row in rows], total, params)


@router.get("/orders/{order_id}")
async def get_order(order_id: uuid.UUID, ctx: Ctx = Depends(require("order.read.self"))) -> dict:
    order = await service.get_order(ctx.session, order_id)
    if not ctx.actor.has("order.read.all") and order.current_assignee_id != ctx.actor.employee_id:
        raise NotFound("Order not found.")
    history = await service.history(ctx.session, order.id)
    return {**_payload(ctx, order), "history": [service.serialize_history(row) for row in history]}


@router.patch("/orders/{order_id}")
async def update_order(
    order_id: uuid.UUID, payload: OrderUpdateRequest, ctx: Ctx = Depends(require("order.update"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    if order.status in service.TERMINAL_STATUSES:
        raise RuleViolation("A delivered or cancelled order cannot be edited.", rule_code="ORDER_TERMINAL")
    changes = payload.model_dump(exclude_unset=True)
    if "order_amount" in changes and changes["order_amount"] is not None:
        changes["order_amount"] = quantize_money(changes["order_amount"])
    if "payment_mode" in changes and changes["payment_mode"] is not None:
        raw_mode = changes["payment_mode"].upper()
        if raw_mode not in PAYMENT_MODES:
            raise ValidationError(f"Unsupported payment mode: {changes['payment_mode']}")
        changes["payment_mode"] = PAYMENT_MODE_MAP.get(raw_mode, "OTHER")
    before = {key: getattr(order, key) for key in changes}
    for key, value in changes.items():
        setattr(order, key, value)
    await ctx.session.flush()
    await ctx.audit(
        category="ORDER",
        action="order.updated",
        entity_type="order",
        entity_id=order.id,
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in changes.items()},
    )
    return _payload(ctx, order)

@router.post("/orders/{order_id}/broadcast")
async def broadcast_order(
    order_id: uuid.UUID, payload: BroadcastRequest, ctx: Ctx = Depends(require("order.broadcast"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    broadcast = await service.broadcast_order(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        audience_scope=payload.audience_scope,
        audience_payload=payload.audience_payload,
        expires_at=payload.expires_at,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.broadcast",
        entity_type="order",
        entity_id=order.id,
        after={"round_no": broadcast.round_no, "audience_scope": broadcast.audience_scope},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.broadcasted.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"round_no": broadcast.round_no},
    )
    return {
        **_payload(ctx, order),
        "broadcast": {
            "id": broadcast.id,
            "round_no": broadcast.round_no,
            "audience_scope": broadcast.audience_scope,
            "broadcast_at": broadcast.broadcast_at,
            "expires_at": broadcast.expires_at,
        },
    }


@router.post("/orders/{order_id}/claim")
async def claim_order(
    order_id: uuid.UUID, request: Request, ctx: Ctx = Depends(require("order.claim"))
) -> dict:
    guard, replay = await begin_idempotency(
        ctx, request, endpoint=f"orders.claim", payload={"order_id": str(order_id)}
    )
    if replay is not None:
        return replay_response(replay)
    employee = await directory_service.get_employee(ctx.session, ctx.employee_id)
    order, claim = await service.claim_order(
        ctx.session,
        order_id=order_id,
        employee=employee,
        actor_user_id=ctx.actor_user_id,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.claimed",
        entity_type="order",
        entity_id=order.id,
        after={"employee_id": str(employee.id), "claim_id": str(claim.id)},
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.claimed.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"employee_id": str(employee.id)},
    )
    body = {**_payload(ctx, order), "claim": service.serialize_claim(claim)}
    await finish_idempotency(guard, 200, body)
    return body


@router.post("/orders/{order_id}/release")
async def release_order(
    order_id: uuid.UUID, payload: ReleaseRequest, ctx: Ctx = Depends(require("order.claim"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    is_holder = order.current_assignee_id == ctx.actor.employee_id
    if not is_holder and not ctx.actor.has("order.reassign"):
        raise PermissionDenied("Only the holder or an administrator may release this order.")
    await service.release_claim(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        employee_id=order.current_assignee_id,
        reason=payload.reason,
        end_reason="RELEASED_BY_EMPLOYEE" if is_holder else "REVOKED_BY_ADMIN",
        rebroadcast=ctx.settings.bool_("orders.allow_rebroadcast_after_release"),
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.claim_released",
        entity_type="order",
        entity_id=order.id,
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.claim_released.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"reason": payload.reason},
    )
    return _payload(ctx, order)


@router.post("/orders/{order_id}/status")
async def update_status(
    order_id: uuid.UUID, payload: StatusRequest, ctx: Ctx = Depends(require("order.update.status.self"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    is_holder = order.current_assignee_id == ctx.actor.employee_id
    can_any = ctx.actor.has("order.update.status.any")
    if not is_holder and not can_any:
        raise PermissionDenied("You do not hold this order.")
    await service.transition_status(
        ctx.session,
        order=order,
        to_status=payload.to_status,
        actor_user_id=ctx.actor_user_id,
        employee_id=ctx.actor.employee_id,
        reason=payload.reason,
        note=payload.note,
        evidence=payload.evidence,
        proof_file_ids=payload.proof_file_ids,
        is_holder=is_holder,
        can_any=can_any,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.status_changed",
        entity_type="order",
        entity_id=order.id,
        after={"status": order.status},
        reason=payload.reason or payload.note,
    )
    from app.platform.service import emit_event

    event_type = "order.delivered.v1" if order.status == "DELIVERED" else "order.status_changed.v1"
    emit_event(
        ctx.session,
        event_type,
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"status": order.status},
    )
    return _payload(ctx, order)


@router.post("/orders/{order_id}/reassign")
async def reassign_order(
    order_id: uuid.UUID, payload: ReassignRequest, ctx: Ctx = Depends(require("order.reassign"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    order, claim = await service.reassign_order(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        new_assignee_employee_id=payload.new_assignee_employee_id,
        reason=payload.reason,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.reassigned",
        entity_type="order",
        entity_id=order.id,
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.reassigned.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"reason": payload.reason},
    )
    body = _payload(ctx, order)
    if claim is not None:
        body["claim"] = service.serialize_claim(claim)
    return body


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: uuid.UUID, payload: CancelRequest, ctx: Ctx = Depends(require("order.cancel"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    await service.cancel_order(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        reason=payload.reason,
        cancellation_code=payload.cancellation_code,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.cancelled",
        entity_type="order",
        entity_id=order.id,
        reason=payload.reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.cancelled.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"reason": payload.reason},
    )
    return _payload(ctx, order)


@router.post("/orders/{order_id}/fail")
async def fail_order(
    order_id: uuid.UUID, payload: FailRequest, ctx: Ctx = Depends(require("order.update.status.self"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    is_holder = order.current_assignee_id == ctx.actor.employee_id
    if not is_holder and not ctx.actor.has("order.update.status.any"):
        raise PermissionDenied("You do not hold this order.")
    await service.fail_order(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        employee_id=ctx.actor.employee_id,
        failure_reason=payload.failure_reason,
        reason_code=payload.reason_code,
        settings=ctx.settings,
    )
    await ctx.audit(
        category="ORDER",
        action="order.failed",
        entity_type="order",
        entity_id=order.id,
        reason=payload.failure_reason,
    )
    from app.platform.service import emit_event

    emit_event(
        ctx.session,
        "order.failed.v1",
        aggregate_type="order",
        aggregate_id=order.id,
        actor_user_id=ctx.actor_user_id,
        payload={"failure_reason": payload.failure_reason},
    )
    return _payload(ctx, order)


@router.post("/orders/{order_id}/attachments", status_code=201)
async def add_attachment(
    order_id: uuid.UUID, payload: AttachmentRequest, ctx: Ctx = Depends(require("order.proof.upload"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    is_holder = order.current_assignee_id == ctx.actor.employee_id
    if not is_holder and not ctx.actor.has("order.update.status.any"):
        raise PermissionDenied("You do not hold this order.")
    evidence = {
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "accuracy_meters": payload.accuracy_meters,
    }
    row = await service.add_attachment(
        ctx.session,
        order=order,
        actor_user_id=ctx.actor_user_id,
        employee_id=ctx.actor.employee_id,
        file_id=payload.file_id,
        purpose=payload.purpose,
        note=payload.note,
        evidence=evidence,
        settings=ctx.settings,
    )
    if payload.customer_confirmed:
        from app.core.timeutil import utcnow

        row.customer_confirmed_at = utcnow()
        row.customer_confirmation_method = payload.customer_confirmation_method
        await ctx.session.flush()
    await ctx.audit(
        category="ORDER",
        action="order.attachment_added",
        entity_type="order_attachment",
        entity_id=row.id,
    )
    return service.serialize_attachment(row)


@router.get("/orders/{order_id}/history")
async def order_history(
    order_id: uuid.UUID, ctx: Ctx = Depends(require("order.read.self"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    if not ctx.actor.has("order.read.all") and order.current_assignee_id != ctx.actor.employee_id:
        raise NotFound("Order not found.")
    rows = await service.history(ctx.session, order.id)
    return {"items": [service.serialize_history(row) for row in rows]}


@router.get("/orders/{order_id}/attachments")
async def list_attachments(
    order_id: uuid.UUID, ctx: Ctx = Depends(require("order.read.self"))
) -> dict:
    order = await service.get_order(ctx.session, order_id)
    if not ctx.actor.has("order.read.all") and order.current_assignee_id != ctx.actor.employee_id:
        raise NotFound("Order not found.")
    attachments = await service.list_attachments(ctx.session, order.id)
    return {"items": [service.serialize_attachment(row) for row in attachments]}